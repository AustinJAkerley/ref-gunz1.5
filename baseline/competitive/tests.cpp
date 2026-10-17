#include "competitive.hpp"
#include "competitive_config.hpp"
#include "damage.hpp"
#include "outbox.hpp"
#include "sqlite3.h"
#include <array>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>

int checks=0;
void check(bool yes,const char* what){++checks;if(!yes)throw std::runtime_error(what);}
void sql(sqlite3* db,const char* text){char* e=nullptr;int rc=sqlite3_exec(db,text,nullptr,nullptr,&e);std::string error=e?e:"";sqlite3_free(e);if(rc!=SQLITE_OK)throw std::runtime_error(error);}
int number(sqlite3* db,const char* text){sqlite3_stmt* s=nullptr;check(sqlite3_prepare_v2(db,text,-1,&s,nullptr)==SQLITE_OK,"prepare scalar");int v=sqlite3_step(s)==SQLITE_ROW?sqlite3_column_int(s,0):-1;sqlite3_finalize(s);return v;}
std::array<int,24> equipment(sqlite3* db,int cid){
    sqlite3_stmt* s=nullptr;sqlite3_prepare_v2(db,"SELECT Items FROM Character WHERE CID=?",-1,&s,nullptr);sqlite3_bind_int(s,1,cid);
    check(sqlite3_step(s)==SQLITE_ROW,"character exists");check(sqlite3_column_bytes(s,0)==96,"item blob layout");
    std::array<int,24> b{};memcpy(b.data(),sqlite3_column_blob(s,0),96);sqlite3_finalize(s);return b;
}
int main(int argc,char** argv)try{
    const char* file=argc>1?argv[1]:":memory:";sqlite3* db=nullptr;check(sqlite3_open(file,&db)==SQLITE_OK,"open");
    sql(db,"CREATE TABLE Character(CID INTEGER PRIMARY KEY,AID INTEGER,Sex INTEGER,Level INTEGER,XP INTEGER,Items BLOB,DeleteFlag INTEGER DEFAULT 0);"
           "CREATE TABLE CharacterItem(CIID INTEGER PRIMARY KEY,CID INTEGER,ItemID INTEGER,RegDate TEXT,Cnt INTEGER,RentHourPeriod INTEGER,RentDate TEXT);"
           "INSERT INTO CharacterItem(CIID,CID,ItemID,RentHourPeriod) VALUES(900,1,25011,24);"
           "INSERT INTO CharacterItem(CIID,CID,ItemID,RentHourPeriod,RentDate) VALUES(901,1,25011,0,'2000-01-01');"
           "INSERT INTO Character(CID,AID,Sex,Level,XP) VALUES(1,1,0,1,0),(2,2,1,2,2),(3,1,0,20,200);");
    competitive::initialize(db);
    check(number(db,"SELECT count(*) FROM Character WHERE Level=99 AND XP>=1101991900")==3,"max-level migration");
    auto male=equipment(db,1),female=equipment(db,2);
    check(male[17]==25011&&male[18]==25011&&male[5]!=male[6],"two independently owned basic rings");
    check(male[20]==6004&&male[21]==6008,"Breaker8 and Breaker9P equipped");
    check(male[22]==52702&&male[23]==52802,"HP and AP packs equipped");
    check(male[12]==48001&&female[12]==48002,"gendered gear");
    check(number(db,"SELECT count(*) FROM CharacterItem WHERE CID=1 AND ItemID IN (4514,4516)")==2,"revolvers owned");
    check(number(db,"SELECT count(*) FROM CharacterItem WHERE CID=1 AND ItemID=25011 AND RentDate IS NULL AND RentHourPeriod IS NULL")==2,"exactly two permanent rings");
    check(male[5]>901&&male[6]>901,"rental and zero-period expired ring not reused as permanent starter");
    int itemCount=number(db,"SELECT count(*) FROM CharacterItem");
    competitive::initialize(db);check(number(db,"SELECT count(*) FROM CharacterItem")==itemCount,"idempotent grant");
    check(equipment(db,1)==male,"reinitialization preserves equipment");
    sql(db,"UPDATE Character SET Level=1,XP=0 WHERE CID=1");
    check(number(db,"SELECT Level FROM Character WHERE CID=1")==99,"level remains capped");
    sql(db,"BEGIN;INSERT INTO Character(CID,AID,Sex,Level,XP) VALUES(4,4,1,99,0)");competitive::grant(db,4,1);sql(db,"COMMIT");
    check(equipment(db,4)[17]==25011,"new-character same transaction grant");
    sql(db,"BEGIN;INSERT INTO Character(CID,AID,Sex,Level,XP) VALUES(5,5,0,99,0)");competitive::grant(db,5,0);sql(db,"ROLLBACK");
    check(number(db,"SELECT count(*) FROM CompetitiveStarter WHERE CID=5")==0,"failed character creation rolls back marker/items");
    check(competitive::delta(1000,1000)==16,"equal Elo delta");
    check(competitive::delta(800,1400)>competitive::delta(1400,800),"upset has greater gain");
    auto outcome=competitive::record(db,"session:round1",1,2,"kill");check(outcome.applied&&outcome.change==16,"result applied");
    check(number(db,"SELECT Elo FROM DuelRating WHERE CID=1")==1016,"winner rating");
    check(number(db,"SELECT Elo FROM DuelRating WHERE CID=2")==984,"loser rating");
    check(!competitive::record(db,"session:round1",1,2,"forfeit").applied,"kill plus disconnect not double-rated");
    check(!competitive::record(db,"same-account",1,3,"kill").applied,"self-farming rejected");
    check(!competitive::record(db,"same-char",1,1,"kill").applied,"same char rejected");
    check(!competitive::record(db,"missing",1,999,"kill").applied,"missing char rejected");
    check(competitive::record(db,"session:round2",2,1,"forfeit").applied,"forfeit recorded");
    int events=number(db,"SELECT count(*) FROM DuelResult");
    sql(db,"CREATE TRIGGER SimulatedFailure BEFORE UPDATE ON DuelRating WHEN NEW.CID=2 BEGIN SELECT RAISE(ABORT,'test failure'); END;");
    bool failed=false;try{competitive::record(db,"atomic",1,2,"kill");}catch(const std::exception&){failed=true;}
    check(failed,"injected update failure");check(number(db,"SELECT count(*) FROM DuelResult")==events,"failed Elo write rolls back event");
    check(number(db,"SELECT sum(Elo) FROM DuelRating WHERE CID IN (1,2)")==2000,"atomic zero-sum pair");
    sql(db,"DROP TRIGGER SimulatedFailure");
    // Exercise the actual durable queue: contention, restart and commit-before-ack.
    sqlite3* journal=nullptr;
    const std::string journalFile=argc>1?std::string(file)+".pending":":memory:";
    check(sqlite3_open(journalFile.c_str(),&journal)==SQLITE_OK,"open outbox");
    competitive::initializeOutbox(journal);
    competitive::enqueue(journal,{"retry-first",1,2,"kill"});
    competitive::enqueue(journal,{"retry-second",2,1,"forfeit"});
    competitive::enqueue(journal,{"retry-first",1,2,"kill"});
    check(number(journal,"SELECT count(*) FROM PendingDuel")==2,"outbox submission idempotent");
    competitive::PendingResult pending;
    check(competitive::oldest(journal,pending)&&pending.event=="retry-first","FIFO round order");
    if(argc>1){
        sqlite3* lock=nullptr;check(sqlite3_open(file,&lock)==SQLITE_OK,"open competing writer");sql(lock,"BEGIN IMMEDIATE");
        bool busy=false;try{competitive::record(db,pending.event,pending.winner,pending.loser,pending.reason.c_str());}catch(const std::exception&){busy=true;}
        check(busy,"game DB contention fails without losing journal");sql(lock,"ROLLBACK");sqlite3_close(lock);
        sqlite3_close(journal);check(sqlite3_open(journalFile.c_str(),&journal)==SQLITE_OK,"reopen outbox after restart");
        check(competitive::oldest(journal,pending)&&pending.event=="retry-first","pending result survives restart");
    }
    check(competitive::record(db,pending.event,pending.winner,pending.loser,pending.reason.c_str()).applied,"retry eventually commits");
    check(!competitive::record(db,pending.event,pending.winner,pending.loser,pending.reason.c_str()).applied,"crash before acknowledgement cannot double-rate");
    competitive::acknowledge(journal,pending.event);
    check(competitive::oldest(journal,pending)&&pending.event=="retry-second","second round follows first");
    check(competitive::record(db,pending.event,pending.winner,pending.loser,pending.reason.c_str()).applied,"second round commits");
    competitive::acknowledge(journal,pending.event);check(!competitive::oldest(journal,pending),"queue drained");sqlite3_close(journal);
    events=number(db,"SELECT count(*) FROM DuelResult");
    auto ladder=competitive::ladder(db);int ranked=0;for(auto r:ladder)if(r.place)++ranked;
    check(ranked==2,"only completed-duel characters receive ladder positions");
    check(competitive::rank(900,0)==competitive::Rank::Iron,"Iron threshold");
    check(competitive::rank(1000,0)==competitive::Rank::Bronze,"Bronze threshold");
    check(competitive::rank(1200,0)==competitive::Rank::Silver,"Silver threshold");
    check(competitive::rank(1500,11)==competitive::Rank::Gold,"Gold threshold");
    check(competitive::rank(1000,10)==competitive::Rank::Top10&&competitive::rank(1000,1)==competitive::Rank::First,"ladder ranks override tiers");
    competitive::DamageConfirmation hit;
    hit.add(0,10,false);check(!hit.visible(10),"no marker for miss");
    hit.add(108,100,false);check(hit.amount==108&&hit.visible(749)&&!hit.visible(750),"shotgun total and expiry");
    hit.add(20,800,true);hit.add(15,820,true);check(hit.amount==35,"server per-target receipts aggregate");
    hit.add(9,1000,false);check(hit.amount==9&&!hit.serverConfirmed,"next local shot replaces marker");
    hit.clear();check(!hit.visible(1001),"clear feedback between games");
    sqlite3_close(db);db=nullptr;
    if(argc>1){check(sqlite3_open(file,&db)==SQLITE_OK,"reopen");check(number(db,"SELECT count(*) FROM DuelResult")==events,"rating history persists");competitive::initialize(db);check(number(db,"SELECT count(*) FROM CharacterItem WHERE CID=1 AND ItemID=25011 AND RentDate IS NULL AND RentHourPeriod IS NULL")==2,"no duplication on process restart");sqlite3_close(db);}
    std::cout<<checks<<" competitive persistence/damage checks passed\n";return 0;
}catch(const std::exception& e){std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;}