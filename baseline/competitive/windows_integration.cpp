// Actual patched server database integration: isolated scratch DB, no game UI.
#include <cassert>
#include "SQLiteDatabase.h"
#include "MMatchTransDataType.h"
#include "MMatchItem.h"
#include "sqlite3.h"
#include <stdexcept>
#include <cstdio>
#include <cstring>
#include <memory>
#include <vector>
#include "MCommand.h"
#include "MCommandCommunicator.h"
#include "MSharedCommandTable.h"
#include "MBlobArray.h"
#include "client.hpp"
#include "MMatchStringResManager.h"
#include "MMatchWorldItemDesc.h"
#include "MZFileSystem.h"

static void require(bool condition,const char* why){if(!condition)throw std::runtime_error(why);}
static void execute(sqlite3* db,const char* query){require(sqlite3_exec(db,query,nullptr,nullptr,nullptr)==SQLITE_OK,sqlite3_errmsg(db));}
static int value(sqlite3* db,const char* query){sqlite3_stmt* s=nullptr;require(sqlite3_prepare_v2(db,query,-1,&s,nullptr)==SQLITE_OK,"query prepare");require(sqlite3_step(s)==SQLITE_ROW,"query result");int n=sqlite3_column_int(s,0);sqlite3_finalize(s);return n;}
class WireCommunicator final:public MCommandCommunicator {
public:
    int Connect(MCommObject*) override{return 0;}
    void Disconnect(MUID) override{}
protected:
    void SendCommand(MCommand*) override{}
    void OnRegisterCommand(MCommandManager* manager) override{MAddSharedCommandTable(manager,MSharedCommandType::All);}
};
static std::vector<char> serialize(MCommand& command){
    require(command.CheckRule(),"wire schema");std::vector<char> data(command.GetSize());
    require(command.GetData(data.data(),int(data.size()))==int(data.size()),"serialize command");
    unsigned short id=0;memcpy(&id,data.data()+2,2);require(id==command.GetID(),"unsigned 16-bit ID roundtrip");return data;
}
static void wireTest(){
    WireCommunicator communicator;require(communicator.Create(),"register complete shared command table");
    auto& manager=*communicator.GetCommandManager();
    for(int id:{MC_MATCH_DUEL_RATING,MC_MATCH_DAMAGE_CONFIRMATION}){
        auto* desc=manager.GetCommandDescByID(id);
        require(desc&&desc->IsFlag(MCDT_MACHINE2MACHINE)&&!desc->IsFlag(MCDT_PEER2PEER),"server command registration");
        require(desc->GetParameterDescCount()==1&&desc->GetParameterType(0)==(id==MC_MATCH_DUEL_RATING?MPT_BLOB:MPT_INT),"noncolliding command schema");
    }
    const MUID sender(1,2),receiver(3,4);
    const CompetitiveRatingWire expected{5,6,1234,2,7,11,3};
    auto blob=MMakeBlobArrayPtr(sizeof(expected),1);memcpy(MGetBlobArrayElement(blob.get(),0),&expected,sizeof(expected));
    MCommand rating(MC_MATCH_DUEL_RATING,sender,receiver,&manager);
    rating.AddParameter(new MCmdParamBlob(blob.get(),MGetBlobArraySize(blob.get())));
    auto ratingBytes=serialize(rating);MCommand decoded;
    require(decoded.SetData(ratingBytes.data(),&manager,static_cast<unsigned short>(ratingBytes.size()))&&decoded.CheckRule(),"deserialize rating");
    CompetitiveReceive(&decoded);require(CompetitiveText(MUID(5,6))=="1234 Silver","actual client rating display");
    MCommand damage(MC_MATCH_DAMAGE_CONFIRMATION,sender,receiver,&manager);damage.AddParameter(new MCmdParamInt(37));
    auto damageBytes=serialize(damage);MCommand decodedDamage;int amount=0;
    require(decodedDamage.SetData(damageBytes.data(),&manager,static_cast<unsigned short>(damageBytes.size()))&&decodedDamage.GetParameter(&amount,0,MPT_INT)&&amount==37,"damage receipt roundtrip");
    for(const auto& bytes:{ratingBytes,damageBytes}){
        std::unique_ptr<MCommand> tunneled(communicator.MakeCmdFromSaneTunnelingBlob(sender,receiver,bytes.data(),bytes.size()));
        require(!tunneled,"machine command cannot impersonate server through peer tunnel");
    }
    MCommand peer(MC_PEER_SPEC,sender,receiver,&manager);auto peerBytes=serialize(peer);
    std::unique_ptr<MCommand> tunneled(communicator.MakeCmdFromSaneTunnelingBlob(sender,receiver,peerBytes.data(),peerBytes.size()));
    require(tunneled&&tunneled->GetID()==MC_PEER_SPEC,"original peer traffic still accepted");
    CompetitiveClear();require(CompetitiveText(MUID(5,6))=="--","client cache reset");
    puts("PASS: full command table, unsigned IDs, real wire/client rating display, damage receipt and peer tunnel trust");
}
static void xmlTest(const std::string& root){
    MMatchStringResManager::MakeInstance();
    MZFileSystem files;require(files.Create(root+"/client"),"client fixture filesystem");
    MMatchItemDescMgr serverItems,clientItems;
    require(serverItems.ReadXml((root+"/server/zitem.xml").c_str()),"actual server item XML loader");
    require(clientItems.ReadXml(&files,"system/zitem.xml"),"actual client item XML loader");
    for(auto* items:{&serverItems,&clientItems}){
        for(int id:{2,6004,6008,4514,4516,48001,48002,52702,52802})
            require(items->GetItemDesc(id)!=nullptr,"original starter descriptor retained");
        auto* ring=items->GetItemDesc(25011);
        require(ring&&ring->m_nHP==10&&ring->m_nAP==10&&ring->m_nType==MMIT_EQUIPMENT&&ring->m_nSlot==MMIST_FINGER,"real loader basic ring stats/type/slot");
    }
    MMatchWorldItemDescMgr serverWorld,clientWorld;
    require(serverWorld.ReadXml((root+"/server/worlditem.xml").c_str()),"actual server world-item loader");
    require(clientWorld.ReadXml(&files,"system/worlditem.xml"),"actual client world-item loader");
    for(auto* items:{&serverWorld,&clientWorld}){
        auto* hp=items->GetItemDesc(130);auto* ap=items->GetItemDesc(131);
        require(hp&&ap&&hp->m_nItemType==WIT_HP&&ap->m_nItemType==WIT_AP&&hp->m_fAmount==20&&ap->m_fAmount==20,"real loader typed 20-point packs");
    }
    char prefixed[]="<ns0:XML xmlns:ns0=\"http://tempuri.org/zitem.xsd\"><ns0:ITEM id=\"25011\" /></ns0:XML>";
    MXmlDocument bad;require(!bad.LoadFromMemory(prefixed),"regression reproduces legacy namespace-prefix rejection");
    MBaseStringResManager::FreeInstance();
    puts("PASS: real client/server XML loaders, original weapons, Basic Ring and 20-point HP/AP packs");
}
int main(int argc,char** argv)try{
    if(argc==3&&std::strcmp(argv[1],"--xml-test")==0){xmlTest(argv[2]);return 0;}
    if(argc==2&&std::strcmp(argv[1],"--wire-test")==0){wireTest();return 0;}
    require(argc==2,"Pass a fresh scratch database filename");
    FILE* existing=fopen(argv[1],"rb");if(existing){fclose(existing);throw std::runtime_error("Refusing existing database");}
    {SQLiteDatabase database(argv[1]);
     require(database.CreateCharacter(101,"FixtureMale",0,0,0,0,0)==0,"original male creation");
     require(database.CreateCharacter(102,"FixtureFemale",0,1,0,0,0)==0,"original female creation");}
    sqlite3* db=nullptr;require(sqlite3_open(argv[1],&db)==SQLITE_OK,"open fixture");
    require(value(db,"SELECT count(*) FROM Character WHERE Level=99 AND length(Items)=96")==2,"level and blob persisted");
    require(value(db,"SELECT count(*) FROM CharacterItem WHERE ItemID=25011")==4,"two basic rings each");
    require(value(db,"SELECT count(*) FROM CharacterItem WHERE ItemID IN (52702,52802)")==4,"both packs each");
    require(value(db,"SELECT count(*) FROM DuelRating WHERE Elo=1000")==2,"initial Elo rows");
    sqlite3_close(db);
    {SQLiteDatabase reopened(argv[1]);}
    require(sqlite3_open(argv[1],&db)==SQLITE_OK,"reopen fixture");
    require(value(db,"SELECT count(*) FROM CharacterItem WHERE ItemID=25011")==4,"no ring duplication on real server DB reconnect");
    execute(db,"UPDATE Character SET Level=1,XP=0");
    require(value(db,"SELECT count(*) FROM Character WHERE Level=99 AND XP>1000000000")==2,"competitive progression floor");
    sqlite3_close(db);
    puts("PASS: real Windows SQLiteDatabase create/reopen, level 99, distinct ring copies, packs and initial Elo");return 0;
}catch(const std::exception& e){fprintf(stderr,"FAIL: %s\n",e.what());return 1;}