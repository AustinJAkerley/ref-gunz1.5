#include "stdafx.h"
#include "server.hpp"
#include "competitive.hpp"
#include "outbox.hpp"
#include "wire.hpp"
#include "MMatchServer.h"
#include "MMatchStage.h"
#include "MBlobArray.h"
#include "MTime.h"
#include "sqlite3.h"
#include <chrono>
#include <random>
#include <unordered_map>
#include <deque>

namespace {
struct Connection {
    sqlite3* db=nullptr;
    explicit Connection(const char* path="GunzDB.sq3",bool outbox=false){
        if(sqlite3_open(path,&db)!=SQLITE_OK){sqlite3_close(db);throw std::runtime_error("Cannot open competitive database");}
        sqlite3_busy_timeout(db,0); // Never wait five seconds on the game thread.
        try{if(outbox)competitive::initializeOutbox(db);}catch(...){sqlite3_close(db);throw;}
    }
    ~Connection(){sqlite3_close(db);}
};
sqlite3* ratingsDB(){
    static Connection c;return c.db;
}
sqlite3* outboxDB(){static Connection c("DuelPending.sq3",true);return c.db;}
bool ratingDirty=true;
std::deque<competitive::PendingResult> pendingResults;
void flushResults(){
    try{
        auto* journal=outboxDB();
        while(!pendingResults.empty()){
            competitive::enqueue(journal,pendingResults.front());pendingResults.pop_front();
        }
        competitive::PendingResult p;
        for(int count=0;count<8&&competitive::oldest(journal,p);++count){
            auto result=competitive::record(ratingsDB(),p.event,p.winner,p.loser,p.reason.c_str());
            if(result.applied){ratingDirty=true;MLog("Duel Elo committed: winner CID %d loser CID %d delta %d (%s)\n",p.winner,p.loser,result.change,p.reason.c_str());}
            competitive::acknowledge(journal,p.event);
        }
    }catch(const std::exception& e){MLog("Duel Elo write will retry in order: %s\n",e.what());}
}
}
void CompetitiveInitialize(sqlite3* db){competitive::initialize(db);}
void CompetitiveGrant(sqlite3* db,int cid,int sex){competitive::grant(db,cid,sex);}
void CompetitiveDamageReceipt(const MMatchObject& attacker,const MUID& victim,int damage){
    if(damage<=0||attacker.GetUID()==victim)return;
    auto* server=MGetMatchServer();auto* cmd=server->CreateCommand(MC_MATCH_DAMAGE_CONFIRMATION,attacker.GetUID());
    cmd->AddParameter(new MCmdParamInt(damage));server->Post(cmd);
}
std::string CompetitiveRoundID(const MUID& stage,int round){
    static const std::string session=[](){std::random_device r;return std::to_string(std::chrono::system_clock::now().time_since_epoch().count())+"-"+std::to_string(r());}();
    static unsigned long long serial=0;
    return session+":"+std::to_string(stage.High)+":"+std::to_string(stage.Low)+":"+std::to_string(round)+":"+std::to_string(++serial);
}
void CompetitiveResult(MMatchStage* stage,const MUID& winner,const MUID& loser,const std::string& event,const char* reason){
    if(!stage)return;
    auto* w=stage->GetObj(winner);auto* l=stage->GetObj(loser);
    if(!w||!l||!w->GetCharInfo()||!l->GetCharInfo())return;
    if((w->GetPlayerFlags()|l->GetPlayerFlags())&MTD_PlayerFlags_Bot)return;
    pendingResults.push_back({event,int(w->GetCharInfo()->m_nCID),int(l->GetCharInfo()->m_nCID),reason});
    flushResults();
}
void CompetitiveBroadcast(MMatchServer& server){
    static unsigned long long last=0;auto now=GetGlobalTimeMS();
    if(now-last<2000)return;
    last=now;
    flushResults();
    try{
        auto rows=competitive::ladder(ratingsDB());std::unordered_map<int,competitive::Rating> byCID;
        for(const auto& r:rows)byCID[r.cid]=r;
        for(auto& entry:*server.GetStageMap()){
            auto* stage=entry.second;std::vector<CompetitiveRatingWire> values;
            for(auto it=stage->GetObjBegin();it!=stage->GetObjEnd();++it){
                auto* player=it->second;if(!player||!player->GetCharInfo())continue;
                const auto found=byCID.find(player->GetCharInfo()->m_nCID);
                if(found==byCID.end())continue;
                const auto& r=found->second;auto uid=player->GetUID();
                values.push_back({uid.High,uid.Low,r.elo,int(competitive::rank(r.elo,r.place)),r.place,r.wins,r.losses});
            }
            if(values.empty())continue;
            void* blob=MMakeBlobArray(sizeof(CompetitiveRatingWire),int(values.size()));
            for(std::size_t i=0;i<values.size();++i)memcpy(MGetBlobArrayElement(blob,int(i)),&values[i],sizeof(values[i]));
            auto* command=server.CreateCommand(MC_MATCH_DUEL_RATING,MUID(0,0));
            command->AddParameter(new MCmdParamBlob(blob,MGetBlobArraySize(blob)));MEraseBlobArray(blob);
            server.RouteToStage(stage->GetUID(),command);
        }
        ratingDirty=false;
    }catch(const std::exception& e){MLog("Elo broadcast failed: %s\n",e.what());}
}