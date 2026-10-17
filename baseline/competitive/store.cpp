#include "competitive.hpp"
#include "outbox.hpp"
#include "competitive_config.hpp"
#include "sqlite3.h"
#include <array>
#include <cstring>
#include <stdexcept>
#include <utility>
#include <map>

namespace competitive {
namespace {
void sql(sqlite3* db,const std::string& text){
    char* error=nullptr;int rc=sqlite3_exec(db,text.c_str(),nullptr,nullptr,&error);
    if(rc!=SQLITE_OK){std::string message=error?error:sqlite3_errmsg(db);sqlite3_free(error);throw std::runtime_error(message);}
}
class Statement {
    sqlite3* db;sqlite3_stmt* value=nullptr;
public:
    Statement(sqlite3* db,const char* query):db(db){if(sqlite3_prepare_v2(db,query,-1,&value,nullptr)!=SQLITE_OK)throw std::runtime_error(sqlite3_errmsg(db));}
    ~Statement(){sqlite3_finalize(value);}
    void bind(int at,int n){if(sqlite3_bind_int(value,at,n)!=SQLITE_OK)throw std::runtime_error("SQLite int bind");}
    void bind(int at,const std::string& s){if(sqlite3_bind_text(value,at,s.c_str(),int(s.size()),SQLITE_TRANSIENT)!=SQLITE_OK)throw std::runtime_error("SQLite text bind");}
    void blob(int at,const void* data,int size){if(sqlite3_bind_blob(value,at,data,size,SQLITE_TRANSIENT)!=SQLITE_OK)throw std::runtime_error("SQLite blob bind");}
    bool step(){int rc=sqlite3_step(value);if(rc!=SQLITE_ROW&&rc!=SQLITE_DONE)throw std::runtime_error(sqlite3_errmsg(db));return rc==SQLITE_ROW;}
    int get(int col){return sqlite3_column_int(value,col);}
    std::string text(int col){const auto* p=sqlite3_column_text(value,col);return p?reinterpret_cast<const char*>(p):"";}
};
class Transaction {
    sqlite3* db;bool done=false;
public:
    explicit Transaction(sqlite3* db):db(db){sql(db,"BEGIN IMMEDIATE");}
    ~Transaction(){if(!done)sqlite3_exec(db,"ROLLBACK",nullptr,nullptr,nullptr);}
    void commit(){sql(db,"COMMIT");done=true;}
};
int own(sqlite3* db,int cid,int item,int copy=0){
    Statement find(db,"SELECT CIID FROM CharacterItem WHERE CID=? AND ItemID=? AND RentDate IS NULL AND RentHourPeriod IS NULL ORDER BY CIID LIMIT 1 OFFSET ?");
    find.bind(1,cid);find.bind(2,item);find.bind(3,copy);if(find.step())return find.get(0);
    Statement insert(db,"INSERT INTO CharacterItem(CID,ItemID,RegDate,Cnt) VALUES(?,?,datetime('now'),1)");
    insert.bind(1,cid);insert.bind(2,item);insert.step();return int(sqlite3_last_insert_rowid(db));
}
}
// Called inside the original character-create transaction, or initialization's
// migration transaction. Marker and items therefore commit or roll back together.
void grant(sqlite3* db,int cid,int sex){
    if(sex!=0&&sex!=1)throw std::runtime_error("Invalid starter character sex");
    Statement marker(db,"INSERT OR IGNORE INTO CompetitiveStarter(CID,Version) VALUES(?,1)");marker.bind(1,cid);marker.step();
    if(sqlite3_changes(db)==0)return;
    Statement profile(db,"INSERT OR IGNORE INTO DuelRating(CID) VALUES(?)");profile.bind(1,cid);profile.step();
    std::array<std::int32_t,24> blob{};
    const int* equipped=sex==0?maleEquipment:femaleEquipment;
    std::map<int,int> copies;
    for(int slot=0;slot<12;++slot)if(equipped[slot]){blob[slot]=own(db,cid,equipped[slot],copies[equipped[slot]]++);blob[12+slot]=equipped[slot];}
    for(int item:revolvers)own(db,cid,item);
    for(int i=0;i<5;++i)own(db,cid,sex==0?maleAlternate[i]:femaleAlternate[i]);
    Statement update(db,"UPDATE Character SET Level=99,XP=MAX(XP,?),Items=? WHERE CID=?");
    update.bind(1,maxLevelXP);update.blob(2,blob.data(),int(sizeof(blob)));update.bind(3,cid);update.step();
}
void initialize(sqlite3* db){
    Transaction transaction(db);
    sql(db,"CREATE TABLE IF NOT EXISTS CompetitiveStarter(CID INTEGER PRIMARY KEY,Version INTEGER NOT NULL)");
    sql(db,"CREATE TABLE IF NOT EXISTS DuelRating(CID INTEGER PRIMARY KEY,Elo INTEGER NOT NULL DEFAULT 1000 CHECK(Elo>=0),Wins INTEGER NOT NULL DEFAULT 0,Losses INTEGER NOT NULL DEFAULT 0)");
    sql(db,"CREATE TABLE IF NOT EXISTS DuelResult(EventID TEXT PRIMARY KEY,WinnerCID INTEGER NOT NULL,LoserCID INTEGER NOT NULL,WinnerBefore INTEGER NOT NULL,LoserBefore INTEGER NOT NULL,Delta INTEGER NOT NULL,Reason TEXT NOT NULL,CreatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)");
    sql(db,"CREATE INDEX IF NOT EXISTS DuelRatingOrder ON DuelRating(Elo DESC,CID)");
    sql(db,"CREATE TRIGGER IF NOT EXISTS CompetitiveLevel99 AFTER UPDATE OF Level,XP ON Character WHEN NEW.Level<>99 OR NEW.XP<"+std::to_string(maxLevelXP)+" BEGIN UPDATE Character SET Level=99,XP=MAX(XP,"+std::to_string(maxLevelXP)+") WHERE CID=NEW.CID; END");
    std::vector<std::pair<int,int>> characters;
    {Statement q(db,"SELECT CID,Sex FROM Character WHERE COALESCE(DeleteFlag,0)=0");while(q.step())characters.emplace_back(q.get(0),q.get(1));}
    for(auto pair:characters)grant(db,pair.first,pair.second);
    sql(db,"UPDATE Character SET Level=99,XP=MAX(XP,"+std::to_string(maxLevelXP)+") WHERE COALESCE(DeleteFlag,0)=0");
    transaction.commit();
}
Result record(sqlite3* db,const std::string& event,int winner,int loser,const char* reason){
    if(event.empty()||event.size()>180||winner<=0||loser<=0||winner==loser)return {};
    Transaction transaction(db);
    // Exclude deleted characters and same-account self-farming. The rule resolves
    // CIDs from the active pair; P2P deaths still inherit upstream client trust.
    Statement valid(db,"SELECT a.AID,b.AID FROM Character a,Character b WHERE a.CID=? AND b.CID=? AND COALESCE(a.DeleteFlag,0)=0 AND COALESCE(b.DeleteFlag,0)=0");
    valid.bind(1,winner);valid.bind(2,loser);
    if(!valid.step()||valid.get(0)==valid.get(1)){transaction.commit();return {};}
    for(int cid:{winner,loser}){Statement init(db,"INSERT OR IGNORE INTO DuelRating(CID) VALUES(?)");init.bind(1,cid);init.step();}
    Statement ratings(db,"SELECT a.Elo,b.Elo FROM DuelRating a,DuelRating b WHERE a.CID=? AND b.CID=?");
    ratings.bind(1,winner);ratings.bind(2,loser);if(!ratings.step())throw std::runtime_error("Missing Elo pair");
    const int beforeWinner=ratings.get(0),beforeLoser=ratings.get(1),change=delta(beforeWinner,beforeLoser);
    Statement eventInsert(db,"INSERT OR IGNORE INTO DuelResult(EventID,WinnerCID,LoserCID,WinnerBefore,LoserBefore,Delta,Reason) VALUES(?,?,?,?,?,?,?)");
    eventInsert.bind(1,event);eventInsert.bind(2,winner);eventInsert.bind(3,loser);eventInsert.bind(4,beforeWinner);
    eventInsert.bind(5,beforeLoser);eventInsert.bind(6,change);eventInsert.bind(7,std::string(reason));eventInsert.step();
    if(sqlite3_changes(db)==0){transaction.commit();return {};}
    Statement win(db,"UPDATE DuelRating SET Elo=Elo+?,Wins=Wins+1 WHERE CID=?");win.bind(1,change);win.bind(2,winner);win.step();
    Statement loss(db,"UPDATE DuelRating SET Elo=Elo-?,Losses=Losses+1 WHERE CID=?");loss.bind(1,change);loss.bind(2,loser);loss.step();
    transaction.commit();return {true,change};
}
std::vector<Rating> ladder(sqlite3* db){
    Statement query(db,"SELECT r.CID,r.Elo,r.Wins,r.Losses FROM DuelRating r JOIN Character c ON c.CID=r.CID WHERE COALESCE(c.DeleteFlag,0)=0 ORDER BY r.Elo DESC,r.CID ASC");
    std::vector<Rating> result;int place=0;
    while(query.step()){
        Rating r;r.cid=query.get(0);r.elo=query.get(1);r.wins=query.get(2);r.losses=query.get(3);
        // New characters have a tier but do not receive Top10/Rank1 until a result.
        if(r.wins+r.losses>0)r.place=++place;
        result.push_back(r);
    }
    return result;
}
void initializeOutbox(sqlite3* db){
    sql(db,"PRAGMA synchronous=FULL");
    sql(db,"CREATE TABLE IF NOT EXISTS PendingDuel(Sequence INTEGER PRIMARY KEY AUTOINCREMENT,EventID TEXT NOT NULL UNIQUE,WinnerCID INTEGER NOT NULL,LoserCID INTEGER NOT NULL,Reason TEXT NOT NULL)");
}
void enqueue(sqlite3* db,const PendingResult& p){
    Statement insert(db,"INSERT OR IGNORE INTO PendingDuel(EventID,WinnerCID,LoserCID,Reason) VALUES(?,?,?,?)");
    insert.bind(1,p.event);insert.bind(2,p.winner);insert.bind(3,p.loser);insert.bind(4,p.reason);insert.step();
}
bool oldest(sqlite3* db,PendingResult& p){
    Statement q(db,"SELECT EventID,WinnerCID,LoserCID,Reason FROM PendingDuel ORDER BY Sequence LIMIT 1");
    if(!q.step())return false;
    p={q.text(0),q.get(1),q.get(2),q.text(3)};return true;
}
void acknowledge(sqlite3* db,const std::string& event){
    Statement q(db,"DELETE FROM PendingDuel WHERE EventID=?");q.bind(1,event);q.step();
}
}