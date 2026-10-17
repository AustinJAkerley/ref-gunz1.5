#pragma once
#include <string>
struct sqlite3;
class MMatchServer;
class MMatchStage;
class MMatchObject;
struct MUID;
void CompetitiveInitialize(sqlite3* db);
void CompetitiveGrant(sqlite3* db,int cid,int sex);
void CompetitiveBroadcast(MMatchServer& server);
std::string CompetitiveRoundID(const MUID& stage,int round);
void CompetitiveResult(MMatchStage* stage,const MUID& winner,const MUID& loser,const std::string& event,const char* reason);
void CompetitiveDamageReceipt(const MMatchObject& attacker,const MUID& victim,int damage);