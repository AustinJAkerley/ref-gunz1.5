"""Pinned-source/UI/data and extracted native sale fixtures. Never launch GunZ.

Run: python3 -m unittest discover -s baseline/tests -p test_progression.py -v
Only temporary fixtures are written. No build/configure, runtime or DB access.
"""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'build/reference-source/src'
DATA = ROOT / 'build/reference-data'
sys.path.insert(0, str(ROOT / 'baseline/competitive'))
import cosmetics
import data
import patch_source
import progression_patch as progression


def original(name):
    return (SOURCE / name).read_bytes().decode('latin1').replace('\r\n', '\n')


def composed(name):
    # Compatible with main's pending composition: never apply an overlay twice.
    text = original(name)
    base_files = getattr(patch_source, 'BASE_FILES', patch_source.FILES)
    base_changes = getattr(patch_source, 'base_changes', patch_source.changes)
    if name in base_files:
        text = base_changes(name, text)
    try:
        import economy_patch
    except ImportError:
        economy_patch = None
    if economy_patch and name in economy_patch.FILES:
        text = economy_patch.changes(name, text)
    return progression.changes(name, text)


def body(name, signature):
    text = composed(name)
    return extract_body(text, signature)


def extract_body(text, signature):
    a, b = progression.block_span(text, signature)
    return signature + '\n' + text[a:b] + '\n'


def run_fixture(source, args=()):
    """Compile only extracted methods in /tmp, never a game/build target."""
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp)
        (path / 'fixture.cpp').write_text(source)
        subprocess.run(['g++', '-std=c++14', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-parameter', '-I', str(SOURCE / 'sdk/rapidxml/include'),
                        str(path / 'fixture.cpp'), '-o', str(path / 'fixture')], check=True)
        subprocess.run([str(path / 'fixture'), *map(str, args)], check=True)


class ProgressionSourceTests(unittest.TestCase):
    def test_all_real_source_patches_compose_and_reject_drift(self):
        for name in progression.FILES:
            with self.subTest(name=name):
                patched = composed(name)
                self.assertNotEqual(original(name), patched)
                with self.assertRaises(ValueError):
                    progression.changes(name, '')
                with self.assertRaises(ValueError):
                    progression.changes(name, patched)

    def test_balanced_body_ignores_comments_and_strings(self):
        text = 'void f() { const char* a="}\\\"{"; char c=\'}\'; /* } */ // {\n if (1) {} }\nvoid g() {}'
        start, end = progression.block_span(text, 'void f()')
        self.assertEqual(text[end:], '\nvoid g() {}')
        self.assertEqual(text[start], '{')
        for broken in ('void f();', 'void f() {', 'void f() {} void f() {}'):
            with self.assertRaises(ValueError):
                progression.block_span(broken, 'void f()')

    def test_owned_files_do_not_overlap_main_gameplay(self):
        for name in ('Gunz/ZCombatInterface.cpp', 'Gunz/ZGame.cpp', 'Gunz/ZGameInput.cpp',
                     'Gunz/ZMyCharacter.cpp', 'Gunz/ZCharacter.cpp'):
            self.assertNotIn(name, progression.FILES)
        self.assertEqual(len(progression.FILES), len(set(progression.FILES)))

    def test_dynamic_progression_not_blank_labels_with_99(self):
        ui = composed('Gunz/ZGameInterface.cpp')
        for forbidden in ('MSG_CHARINFO_LEVEL', 'MSG_CHARINFO_XP', 'MSG_WORD_LIMITEDLEVEL',
                          'GetLevel()', 'm_nResLevel'):
            self.assertFalse(forbidden in ui, forbidden)
        # Replay restores a cached wire percentage; it is not rendered. Keep it.
        self.assertEqual([line.strip() for line in ui.splitlines() if 'GetLevelPercent()' in line],
                         ['m_nLevelPercentCache = ZGetMyInfo()->GetLevelPercent();'])
        player = composed('Gunz/ZPlayerListBox.cpp')
        self.assertNotIn('"%2d", nLevel', player)
        self.assertIn('m_Fields.Get(1)->nTabSize = 0;', player)
        self.assertNotIn('pAccountCharInfo->nLevel, ZMsg', composed('Gunz/ZCharacterSelectView.cpp'))
        self.assertNotIn('return m_szLevel', composed('Gunz/ZEquipmentListBox.h'))
        self.assertNotIn('itoa_safe(nLevel', composed('Gunz/ZEquipmentListBox.cpp'))
        self.assertNotIn('GetBountyValue()', composed('Gunz/ZMyItemList.cpp'))

    def test_room_filters_and_requirements_are_gone(self):
        stage = composed('Gunz/ZStageSetting.cpp')
        self.assertNotIn('"StageLevelLimit"', stage)
        self.assertIn('pOutNode->nLimitLevel = 0;', stage)
        self.assertNotIn('"%d~%d"', composed('Gunz/ZRoomListBox.cpp'))
        self.assertNotIn('m_nResLevel', composed('Gunz/ZItemSlotView.cpp'))
        self.assertNotIn('MSG_CHARINFO_LEVEL', composed('Gunz/ZStageInterface.cpp'))

    def test_hud_preserves_hit_and_hp_ap(self):
        text = composed('Gunz/ZScreenEffectManager.cpp')
        self.assertIn('DrawDamageHit();', text)
        self.assertIn('CompetitiveDamage().visible', text)
        self.assertIn('m_pHPPanel->Draw(0);', text)
        self.assertIn('min(1.f,m_fGuageHP)', text)
        self.assertIn('min(1.f,m_fGuageAP)', text)
        self.assertNotIn('min(1.f,m_fGuageEXP)', text)
        self.assertNotIn('PlaySoundScoreGet();', body('Gunz/ZScreenEffectManager.cpp',
                                                    'void ZScreenEffectManager::AddExpEffect(int nExp)'))
        self.assertNotIn('MSG_GAME_LEVEL_', composed('Gunz/ZGameClient.cpp'))

    def test_server_catalogue_remains_authoritative(self):
        text = composed('MatchServer/MMatchServer_Item.cpp')
        self.assertIn('if (MGetMatchShop()->IsSellItem(nItemID) == false) return false;', text)
        self.assertIn('pObject->GetCharInfo()->m_nBP < nPrice', text)
        self.assertIn('BuyBountyItem(', text)
        self.assertNotIn('SellBountyItem(', text)
        self.assertNotIn('GetBountyValue()', body('MatchServer/MMatchServer_Quest.cpp',
            'void MMatchServer::OnResponseSellQuestItem( const MUID& uidSender, const u32 nItemID, const int nCount )'))
        # No price multipliers, level-based purchases, or alternative catalogue.
        for name, signature in (
            ('MatchServer/MMatchServer_Item.cpp', 'bool MMatchServer::BuyItem(MMatchObject* pObject, unsigned int nItemID, bool bRentItem, int nRentPeriodHour)'),
            ('MatchServer/MMatchServer_Item.cpp', 'bool MMatchServer::ResponseBuyItem(const MUID& uidPlayer, const u32 nItemID)'),
            ('MatchServer/MMatchServer_Quest.cpp', 'void MMatchServer::OnResponseBuyQeustItem( const MUID& uidSender, const u32 nItemID )'),
        ):
            purchase = body(name, signature)
            self.assertEqual(purchase, extract_body(original(name), signature))
            self.assertNotRegex(purchase, r'm_nLevel|m_nResLevel|GetLevel')

    def test_server_filters_normalize_and_keep_elo_and_floor(self):
        server = composed('MatchServer/MMatchServer.cpp')
        for forbidden in ('GetLimitLevel()', 'GetLevelMin()', 'GetLevelMax()',
                          'MERR_CANNOT_JOIN_CHANNEL_BY_NEWBIE', 'MERR_LOW_LEVEL'):
            self.assertFalse(forbidden in server, forbidden)
        self.assertIn('CompetitiveGBucksTick(*this);\n\tCompetitiveBroadcast(*this);', server)
        stage = composed('MatchServer/MMatchServer_Stage.cpp')
        self.assertIn('pNode->nLimitLevel = 0; // Ignore legacy room progression filters.\n'
                      '\tpSetting->UpdateStageSetting(pNode);', stage)
        self.assertNotIn('MSTAGENODE_FLAG_LIMITLEVEL', stage)
        self.assertNotIn('GetLimitLevel()', stage)
        signature = 'void MMatchServer::ResponseQuickJoin(const MUID& uidPlayer, MTD_QuickJoinParam* pQuickJoinParam)'
        self.assertEqual(body('MatchServer/MMatchServer_Stage.cpp', signature),
                         extract_body(original('MatchServer/MMatchServer_Stage.cpp'), signature))
        channel = composed('MatchServer/MMatchServer_Channel.cpp')
        self.assertNotIn('GetLevelMin()', channel)
        self.assertIn('ValidateChannelJoin(uidComm, uid)', channel)
        clan = composed('MatchServer/MMatchServer_Clan.cpp')
        self.assertNotIn('CLAN_CREATING_NEED_LEVEL', clan)
        self.assertIn('CLAN_CREATING_NEED_BOUNTY', clan)
        self.assertIn('MERR_CLAN_NO_SPONSOR', clan)
        self.assertNotIn('m_nResLevel', composed('MatchServer/MMatchServer_Char.cpp'))
        # No change to Elo implementation, DB floors, or combat-owned renderers.
        self.assertNotIn('MatchServer/SQLiteDatabase.cpp', progression.FILES)
        self.assertNotIn('MatchServer/MMatchRuleDuel.cpp', progression.FILES)
        self.assertNotIn('MatchServer/MMatchFormula.cpp', progression.FILES)

    @unittest.skipUnless(shutil.which('g++'), 'native fixture compiler unavailable')
    def test_real_validators_and_quickjoin_ignore_levels_not_other_guards(self):
        source = r'''
#include <cassert>
#include <cstdlib>
#include <list>
#include <vector>
using std::list;
using u32 = unsigned;
struct MUID { int value; MUID(int a=0,int b=0):value(a+b){} };
enum { MOK, MERR_CANNOT_JOIN_STAGE, MERR_CANNOT_JOIN_STAGE_BY_MAXPLAYERS,
 MERR_CANNOT_JOIN_STAGE_BY_FORCEDENTRY, MERR_CANNOT_JOIN_STAGE_BY_BAN,
 MERR_CANNOT_JOIN_CHANNEL, MERR_CANNOT_JOIN_CHANNEL_BY_MAXPLAYERS,
 MERR_UNKNOWN, MERR_CANNOT_EQUIP_ITEM, MERR_TOO_HEAVY, MERR_CANNOT_EQUIP_EQUAL_ITEM,
 MERR_CANNOT_NO_STAGE, MC_MATCH_STAGE_RESPONSE_QUICKJOIN };
enum { STAGE_STATE_CLOSE, STAGE_STATE_STANDBY, STAGE_STATE_RUN, MSM_EVENT=9 };
enum MMatchSex { MMS_MALE, MMS_FEMALE };
enum MMatchCharItemParts { MMCIP_PRIMARY, MMCIP_SECONDARY, MMCIP_MELEE };
struct MMatchItemDesc { int m_nResSex=-1, m_nResLevel=10000, m_nWeight=1, m_nMaxWT=0; };
struct Descriptors { MMatchItemDesc item; MMatchItemDesc* GetItemDesc(u32 id){return id?&item:nullptr;} } descriptors;
Descriptors* MGetMatchItemDescMgr(){return &descriptors;}
struct Config { int mode=0; int GetServerMode(){return mode;} } config;
Config* MGetServerConfig(){return &config;}
struct MMatchItem { u32 id=1; u32 GetDescID(){return id;} MMatchItemDesc* GetDesc(){return descriptors.GetItemDesc(id);} };
struct MMatchEquipedItem {
 MMatchItem* items[3]{};
 bool IsEmpty(MMatchCharItemParts p){return !items[p];}
 MMatchItem* GetItem(MMatchCharItemParts p){return items[p];}
};
struct Info {
 int m_nLevel=99,m_nCID=1,weight=0,maxWeight=10; MMatchSex m_nSex=MMS_MALE;
 MMatchEquipedItem m_EquipedItem;
 void GetTotalWeight(int* w,int* m){*w=weight;*m=maxWeight;}
};
struct MMatchObject {
 Info info; bool enabled=true,admin=false;
 Info* GetCharInfo(){return &info;}
 MUID GetUID(){return MUID(1);} MUID GetChannelUID(){return MUID(2);}
};
bool IsEnabledObject(MMatchObject* p){return p && p->enabled;}
bool IsAdminGrade(MMatchObject* p){return p->admin;}
struct Setting {
 int max=2,limit=5,map=1,mode=2; bool forced=true;
 int GetMaxPlayers(){return max;} bool GetForcedEntry(){return forced;}
 int GetMapIndex(){return map;} int GetGameType(){return mode;}
};
struct MMatchStage {
 Setting settings; int state=STAGE_STATE_STANDBY,players=0; bool banned=false,priv=false;
 int GetState(){return state;} Setting* GetStageSetting(){return &settings;}
 int GetCountableObjCount(){return players;} bool CheckBanList(int){return banned;}
 bool IsPrivate(){return priv;} MUID GetUID(){return MUID(3);}
};
struct MMatchChannel {
 int players=0,max=10; MMatchStage* stage=nullptr;
 int GetObjCount(){return players;} int GetMaxPlayers(){return max;}
 int GetMaxStages(){return 1;} bool IsEmptyStage(int){return !stage;}
 MMatchStage* GetStage(int){return stage;}
 // Deliberately no GetLevelMin/Max, IsNewbie or master-level API: use must fail.
};
struct MTD_QuickJoinParam { unsigned nMapEnum=~0u,nModeEnum=~0u; };
bool CheckBitSet(unsigned mask,int bit){return (mask & (1u<<bit))!=0;}
struct MCommandParameterInt { int value; explicit MCommandParameterInt(int v):value(v){} };
struct MCommandParameterUID { MUID value; explicit MCommandParameterUID(MUID v):value(v){} };
struct MCommand {
 int result=-1; MUID stage;
 void AddParameter(MCommandParameterInt* p){result=p->value;delete p;}
 void AddParameter(MCommandParameterUID* p){stage=p->value;delete p;}
};
struct MMatchServer {
 MMatchObject player; MMatchStage stage; MMatchChannel channel; MCommand last;
 MMatchServer(){channel.stage=&stage;}
 MMatchObject* GetObject(MUID id){return id.value==1?&player:nullptr;}
 MMatchStage* FindStage(MUID id){return id.value==3?&stage:nullptr;}
 MMatchChannel* FindChannel(MUID id){return id.value==2?&channel:nullptr;}
 MCommand* CreateCommand(int,MUID){return new MCommand;}
 void RouteToListener(MMatchObject*,MCommand* c){last=*c;delete c;}
 int ValidateStageJoin(const MUID&,const MUID&);
 int ValidateChannelJoin(const MUID&,const MUID&);
 int ValidateEquipItem(MMatchObject*,MMatchItem*,const MMatchCharItemParts);
 bool CorrectEquipmentByLevel(MMatchObject*,MMatchCharItemParts,int);
 void ResponseQuickJoin(const MUID&,MTD_QuickJoinParam*);
};
'''
        specs = [
            ('MatchServer/MMatchObject.cpp', 'bool IsEquipableItem(u32 nItemID, int nPlayerLevel, MMatchSex nPlayerSex)'),
            ('MatchServer/MMatchServer.cpp', 'int MMatchServer::ValidateStageJoin(const MUID& uidPlayer, const MUID& uidStage)'),
            ('MatchServer/MMatchServer.cpp', 'int MMatchServer::ValidateChannelJoin(const MUID& uidPlayer, const MUID& uidChannel)'),
            ('MatchServer/MMatchServer.cpp', 'int MMatchServer::ValidateEquipItem(MMatchObject* pObj, MMatchItem* pItem, const MMatchCharItemParts parts)'),
            ('MatchServer/MMatchServer_Char.cpp', 'bool MMatchServer::CorrectEquipmentByLevel(MMatchObject* pPlayer, MMatchCharItemParts nPart, int nLegalItemLevelDiff)'),
            ('MatchServer/MMatchServer_Stage.cpp', 'void MMatchServer::ResponseQuickJoin(const MUID& uidPlayer, MTD_QuickJoinParam* pQuickJoinParam)'),
        ]
        source += ''.join(body(*spec) for spec in specs)
        source += r'''
int main(){
 MMatchServer s; MMatchItem item; MTD_QuickJoinParam param;
 for(int level: {0,1,5,20,99,100,10000}) {
  s.player.info.m_nLevel=level;
  for(int requirement: {0,1,99,100,10000}) {
   descriptors.item.m_nResLevel=requirement;
    for(int mode: {0,int(MSM_EVENT)}) {
    config.mode=mode;
    assert(s.ValidateEquipItem(&s.player,&item,MMCIP_PRIMARY)==MOK);
    assert(!s.CorrectEquipmentByLevel(&s.player,MMCIP_PRIMARY,0));
   }
  }
  for(int limit: {-1,0,5,10000}) {
   s.stage.settings.limit=limit;
   assert(s.ValidateStageJoin(1,3)==MOK);
   assert(s.ValidateChannelJoin(1,2)==MOK);
   s.ResponseQuickJoin(1,&param);
   assert(s.last.result==MOK && s.last.stage.value==3);
  }
 }
 assert(s.ValidateStageJoin(0,3)==MERR_CANNOT_JOIN_STAGE);
 assert(s.ValidateStageJoin(1,0)==MERR_CANNOT_JOIN_STAGE);
 assert(s.ValidateChannelJoin(0,2)==MERR_CANNOT_JOIN_CHANNEL);
 assert(s.ValidateChannelJoin(1,0)==MERR_CANNOT_JOIN_CHANNEL);
 assert(s.ValidateEquipItem(nullptr,&item,MMCIP_PRIMARY)==MERR_UNKNOWN);
 assert(s.ValidateEquipItem(&s.player,nullptr,MMCIP_PRIMARY)==MERR_UNKNOWN);
 auto noQuickJoin=[&](){s.ResponseQuickJoin(1,&param);assert(s.last.result==MERR_CANNOT_NO_STAGE && s.last.stage.value==0);};
 s.stage.players=2;
 assert(s.ValidateStageJoin(1,3)==MERR_CANNOT_JOIN_STAGE_BY_MAXPLAYERS); noQuickJoin();
 s.stage.players=0; s.stage.state=STAGE_STATE_CLOSE;
 assert(s.ValidateStageJoin(1,3)==MERR_CANNOT_JOIN_STAGE); noQuickJoin();
 s.stage.state=STAGE_STATE_RUN;s.stage.settings.forced=false;
 assert(s.ValidateStageJoin(1,3)==MERR_CANNOT_JOIN_STAGE_BY_FORCEDENTRY); noQuickJoin();
 s.stage.settings.forced=true;s.stage.banned=true;
 assert(s.ValidateStageJoin(1,3)==MERR_CANNOT_JOIN_STAGE_BY_BAN);noQuickJoin();
 s.stage.banned=false;s.stage.priv=true;noQuickJoin();s.stage.priv=false;
 param.nMapEnum=0;noQuickJoin();param.nMapEnum=~0u;param.nModeEnum=0;noQuickJoin();param.nModeEnum=~0u;
 s.channel.players=s.channel.max;
 assert(s.ValidateChannelJoin(1,2)==MERR_CANNOT_JOIN_CHANNEL_BY_MAXPLAYERS);
 item.id=0;assert(s.ValidateEquipItem(&s.player,&item,MMCIP_PRIMARY)==MERR_CANNOT_EQUIP_ITEM);item.id=1;
 descriptors.item.m_nResSex=MMS_FEMALE;
 assert(s.ValidateEquipItem(&s.player,&item,MMCIP_PRIMARY)==MERR_CANNOT_EQUIP_ITEM);
 descriptors.item.m_nResSex=-1;descriptors.item.m_nWeight=11;
 assert(s.ValidateEquipItem(&s.player,&item,MMCIP_PRIMARY)==MERR_TOO_HEAVY);
 descriptors.item.m_nWeight=1;s.player.info.m_EquipedItem.items[MMCIP_SECONDARY]=&item;
 assert(s.ValidateEquipItem(&s.player,&item,MMCIP_PRIMARY)==MERR_CANNOT_EQUIP_EQUAL_ITEM);
}
'''
        run_fixture(source)

    @unittest.skipUnless(shutil.which('g++'), 'native fixture compiler unavailable')
    def test_removed_shop_widgets_are_safe_for_real_show_and_tab_methods(self):
        source = r'''
#include <array>
#include <cassert>
#include <cstring>
#include <map>
#include <string>
struct MWidget { bool shown=false,enabled=false; void Show(bool b,bool=false){shown=b;} void Enable(bool b){enabled=b;} };
using MButton=MWidget;
struct MBitmap {};
struct MPicture:MWidget {void SetBitmap(MBitmap*){}};
struct MComboBox:MWidget {int GetSelIndex(){return 10;}};
struct ZIDLResource {
 std::map<std::string,MWidget*> widgets;
 MWidget* FindWidget(const char* name){auto it=widgets.find(name);return it==widgets.end()?nullptr:it->second;}
};
struct ZMyItemList {int m_ListFilter=0;};
struct MyInfo {ZMyItemList list; ZMyItemList* GetItemList(){return &list;}} info;
MyInfo* ZGetMyInfo(){return &info;}
struct MBitmapManager {static MBitmap* Get(const char*){static MBitmap b;return &b;}};
struct ZGameInterface {
 ZIDLResource m_IDLResource; int m_nShopTabNum=0;
 ZIDLResource* GetIDLResource(){return &m_IDLResource;}
 bool ShowWidget(const char*,bool,bool=false);
 void SelectShopTab(int);
};
'''
        for signature in ('bool ZGameInterface::ShowWidget(const char* szName, bool bVisible, bool bModal)',
                          'void ZGameInterface::SelectShopTab(int nTabIndex)',
                          'static bool DisableWidgets(bool Shop, ZIDLResource* pResource)'):
            source += body('Gunz/ZGameInterface.cpp', signature)
        source += r'''
int main(){
 ZGameInterface ui; MWidget lobby,shop,equipment;MComboBox filter;
 ui.m_IDLResource.widgets={{"Lobby",&lobby},{"Shop",&shop},{"Equipment",&equipment},{"Shop_AllEquipmentFilter",&filter}};
 assert(!ui.ShowWidget("MyAllEquipmentListCaller",true));
 assert(!ui.ShowWidget("SellConfirmCaller",true));
 assert(!ui.ShowWidget("Shop_SellQuestItem",true));
 assert(ui.ShowWidget("Lobby",true) && lobby.shown && !shop.shown && !equipment.shown);
 for(int tab: {0,1,2}) {ui.SelectShopTab(tab);assert(ui.m_nShopTabNum==tab);}
 assert(!DisableWidgets(true,ui.GetIDLResource()));
 assert(!DisableWidgets(false,ui.GetIDLResource()));
 assert(info.list.m_ListFilter==10);
}
'''
        run_fixture(source)
        # All direct uses of the removed sale buttons are guarded. Disabled
        # entry points are tested separately by the sale rejection fixture.
        listbox = composed('Gunz/ZEquipmentListBox.cpp')
        for name in ('SellConfirmCaller', 'SellQuestItemConfirmCaller'):
            matches = re.findall(r'FindWidget\(\s*"' + name + r'"\);\s*if \( pButton\)', listbox)
            self.assertEqual(len(matches), 2, name)
        listener = original('Gunz/ZInterfaceListener.cpp')
        self.assertIn('FindWidget( "Shop_SellQuestItem");\n\tif ( pWidget)\n\t\tpWidget->Show( false);', listener)

    @unittest.skipUnless(shutil.which('g++'), 'native fixture compiler unavailable')
    def test_extracted_real_sale_rejection_and_noop_notifications(self):
        # This compiles only a disposable harness, NOT the game or its build.
        source = r'''
#include <cassert>
#include <vector>
using u32 = unsigned;
struct MUID { int value; MUID(int a=0,int b=0):value(a+b){} };
constexpr int MC_MATCH_RESPONSE_SELL_ITEM=1, MC_MATCH_RESPONSE_SELL_QUEST_ITEM=2;
constexpr int MERR_CANNOT_SELL_ITEM=20005;
struct MCmdParamInt {int value; explicit MCmdParamInt(int v):value(v){} };
struct MCommand {int id; std::vector<int> values;
 void AddParameter(MCmdParamInt* p){values.push_back(p->value);delete p;}};
struct Info {int m_nBP=739; int inventory=12;};
struct MMatchObject {Info info; bool enabled=true; Info* GetCharInfo(){return &info;}};
bool IsEnabledObject(MMatchObject* p){return p && p->enabled;}
struct MMatchServer {
 MMatchObject player; int responses=0; MCommand last{};
 MMatchObject* GetObject(MUID uid){return uid.value==1 ? &player : nullptr;}
 MCommand* CreateCommand(int id,MUID){return new MCommand{id,{}};}
 void RouteToListener(MMatchObject*, MCommand* p){++responses;last=*p;delete p;}
 bool ResponseSellItem(const MUID&,const MUID&);
 void OnResponseSellQuestItem(const MUID&,const u32,const int);
};
struct ZObject {};
struct ZEffectManager {void AddLevelUpEffect(ZObject*);};
struct ZScreenEffectManager {void AddExpEffect(int);void SetGuageExpFromMyInfo();};
struct ZGameClient {void OnGameLevelUp(const MUID&);void OnGameLevelDown(const MUID&);};
'''
        specs = [
            ('MatchServer/MMatchServer_Item.cpp', 'bool MMatchServer::ResponseSellItem(const MUID& uidPlayer, const MUID& uidItem)'),
            ('MatchServer/MMatchServer_Quest.cpp', 'void MMatchServer::OnResponseSellQuestItem( const MUID& uidSender, const u32 nItemID, const int nCount )'),
            ('Gunz/ZEffectManager.cpp', 'void ZEffectManager::AddLevelUpEffect(ZObject* pObj)'),
            ('Gunz/ZScreenEffectManager.cpp', 'void ZScreenEffectManager::AddExpEffect(int nExp)'),
            ('Gunz/ZScreenEffectManager.cpp', 'void ZScreenEffectManager::SetGuageExpFromMyInfo()'),
            ('Gunz/ZGameClient.cpp', 'void ZGameClient::OnGameLevelUp(const MUID& uidChar)'),
            ('Gunz/ZGameClient.cpp', 'void ZGameClient::OnGameLevelDown(const MUID& uidChar)'),
        ]
        source += ''.join(body(*spec) for spec in specs)
        source += r'''
int main(){
 MMatchServer server;
 for (int i=0;i<1000;++i){
   assert(!server.ResponseSellItem(MUID(1),MUID(i)));
   assert(server.last.id==MC_MATCH_RESPONSE_SELL_ITEM);
   assert(server.last.values==std::vector<int>{MERR_CANNOT_SELL_ITEM});
   server.OnResponseSellQuestItem(MUID(1),unsigned(i),i%2 ? 1000000 : -1000000);
   assert(server.last.id==MC_MATCH_RESPONSE_SELL_QUEST_ITEM);
   assert((server.last.values==std::vector<int>{MERR_CANNOT_SELL_ITEM,739}));
 }
 assert(server.player.info.m_nBP==739 && server.player.info.inventory==12);
 assert(server.responses==2000);
 assert(!server.ResponseSellItem(MUID(0),MUID(1)));
 server.OnResponseSellQuestItem(MUID(0),1,1);
 server.player.enabled=false;
 assert(!server.ResponseSellItem(MUID(1),MUID(1)));
 server.OnResponseSellQuestItem(MUID(1),1,1);
 assert(server.responses==2000);
 ZEffectManager{}.AddLevelUpEffect(nullptr);
 ZScreenEffectManager effects; effects.AddExpEffect(123);effects.AddExpEffect(-456);effects.SetGuageExpFromMyInfo();
 ZGameClient client;client.OnGameLevelUp(MUID(1));client.OnGameLevelDown(MUID(1));
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'fixture.cpp').write_text(source)
            subprocess.run(['g++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                            str(path / 'fixture.cpp'), '-o', str(path / 'fixture')], check=True)
            subprocess.run([str(path / 'fixture')], check=True)


class CosmeticDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name)
        cls.input_paths = [DATA / p for p in ('client/system/zitem.xml', 'server/zitem.xml',
                                             'server/shop.xml', cosmetics.HUD_ART)]
        cls.before = {p: hashlib.sha256(p.read_bytes()).digest() for p in cls.input_paths}
        data.install_items(DATA, cls.output)
        cls.files = cosmetics.install(DATA, cls.output)
        cls.client = {int(e.get('id')): e for e in ET.parse(cls.output / 'client/system/zitem.xml').getroot()}
        cls.server = {int(e.get('id')): e for e in ET.parse(cls.output / 'server/zitem.xml').getroot()}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_actual_namespace_unaware_loader_names(self):
        for relative in self.files:
            if not relative.endswith('.xml'):
                continue
            raw = (self.output / relative).read_bytes()
            names = cosmetics.literal_names(raw)
            self.assertIn(names[0], ('XML', 'xml'), relative)
            if relative.endswith('zitem.xml'):
                self.assertEqual(set(names[1:]), {'ITEM'})
                self.assertIn(b'xmlns="http://tempuri.org/zitem.xsd"', raw)
            if relative == 'server/shop.xml':
                self.assertEqual(set(names[1:]), {'SELL'})
            if '/Interface/' in relative:
                self.assertTrue(all(':' not in n for n in names if not n.endswith(':Schema')))

    def test_complete_gendered_catalogue_price_and_models(self):
        cosmetics.validate(DATA)  # Validates actual loaded model part bytes.
        root = ET.parse(self.output / 'server/shop.xml').getroot()
        ids = [int(e.attrib['itemid']) for e in root.findall('SELL')]
        self.assertEqual(ids, list(cosmetics.CATALOGUE_IDS))
        self.assertEqual(len(ids), 40)
        self.assertEqual(len(set(ids)), 40)
        for sexes in cosmetics.OUTFITS.values():
            for sex, outfit in sexes.items():
                self.assertEqual(sum(int(self.client[i].get('bt_price')) for i in outfit), 500)
                for ident, slot in zip(outfit, cosmetics.SLOTS):
                    item = self.client[ident]
                    self.assertEqual(item.attrib, self.server[ident].attrib)
                    self.assertEqual((item.get('slot'), item.get('res_sex')), (slot, sex))
                    self.assertEqual(item.get('iscashitem'), 'false')
                    self.assertNotIn('admin', item.get('name').lower())
                    self.assertIn('100 GBucks', item.get('desc'))
        for ident in (*range(48001, 48011), 25011, 6004, 6008, 4514, 4516):
            self.assertNotIn(ident, ids)

    def test_uniform_armor_and_no_requirements(self):
        for items in (self.client, self.server):
            for item in items.values():
                self.assertEqual(item.get('res_level'), '0')
                if item.get('slot') in cosmetics.SLOTS:
                    for key, value in cosmetics.ARMOR_STATS.items():
                        self.assertEqual(item.get(key), value, (item.get('id'), key))
                    for key, value in item.attrib.items():
                        if key.endswith('_bonus'):
                            self.assertEqual(value, '0')
        for item in ET.parse(self.output / 'client/system/fg_zitem.xml').getroot():
            self.assertEqual(item.get('res_level'), '0')

    def test_starter_stats_look_and_weapon_stats_preserved(self):
        pinned = {int(e.get('id')): e for e in ET.parse(DATA / 'client/system/zitem.xml').getroot()}
        for ident in range(48001, 48011):
            self.assertEqual(self.client[ident].attrib, pinned[ident].attrib)
        for ident in (2, 6004, 6008, 4514, 4516, 52702, 52802):
            expected = dict(pinned[ident].attrib, res_level='0')
            self.assertEqual(self.client[ident].attrib, expected)
        ring = self.client[25011]
        self.assertEqual((ring.get('hp'), ring.get('ap'), ring.get('weight')), ('10', '10', '0'))

    def test_removed_widgets_and_clear_sale_notice(self):
        for name in cosmetics.UI_FILES:
            root = ET.parse(self.output / 'client/Interface/default' / name).getroot()
            self.assertFalse({e.get('item') for e in root} & cosmetics.HIDDEN_WIDGETS)
            self.assertFalse(any(e.findtext('TEXT') == 'STR:UI_SSF_05' for e in root))
        shop = ET.parse(self.output / 'client/Interface/default/Shop.xml').getroot()
        notice = next(e for e in shop if e.get('item') == 'CompetitiveCosmeticNotice')
        self.assertIn('Selling is disabled', notice.findtext('TEXT'))
        result = ET.parse(self.output / 'client/Interface/default/GameResult.xml').getroot()
        self.assertFalse(any('PlayerScore' in e.get('item', '') for e in result))
        self.assertTrue(any(e.get('item') == 'GameResult_Background' for e in result))
        self.assertTrue(any(e.get('item') == 'QuestResult_GetBounty' for e in result))

    def test_messages_keep_existing_ids_not_xp_to_currency(self):
        messages = {e.get('id'): e.text or '' for e in ET.parse(self.output / 'client/system/messages.xml').getroot()}
        self.assertEqual(messages['1713'], 'GBucks')
        for ident in ('1703', '1712', '1717', '9366', '2002', '2003'):
            self.assertEqual(messages[ident], '')
        self.assertEqual(messages['1704'], 'Winning Percentage')
        for relative in self.files:
            if not relative.endswith(('zitem.xml', *cosmetics.TEXT_FILES)):
                continue
            for e in ET.parse(self.output / relative).getroot().iter():
                visible = (e.text or '') + ' ' + e.get('name', '') + ' ' + e.get('desc', '')
                self.assertNotRegex(visible, r'(?i)\b(?:exp|xp|bounty|BP|experience points|level\s+\d+|level restriction)\b')

    def test_unrelated_tiers_lore_and_nested_tips(self):
        old = {e.get('id'): e.text for e in ET.parse(DATA / 'client/system/strings.xml').getroot()}
        new = {e.get('id'): e.text for e in ET.parse(self.output / 'client/system/strings.xml').getroot()}
        for ident in ('ZITEM_DESC_12', 'ZITEM_DESC_10001', 'ZITEM_DESC_600006', 'ZITEM_DESC_600106'):
            self.assertEqual(new[ident], old[ident], ident)
        for base in ('client/system', 'server'):
            tips = ET.parse(self.output / base / 'tips.xml').getroot()
            self.assertEqual(sum('GBucks buy cosmetic outfits' in (e.text or '') for e in tips.iter('MSG')), 3)
            self.assertTrue(any('Massive Strike' in (e.text or '') for e in tips.iter('MSG')))

    @unittest.skipUnless(shutil.which('g++'), 'native fixture compiler unavailable')
    def test_empty_msg_real_rapidxml_gettext_and_stringres_initialize(self):
        xml_source = original('cml/source/MXml.cpp')
        self.assertIn('Doc.parse<rapidxml::parse_default>(&FileBuffer[0], FileBuffer.size());', xml_source)
        source = r'''
#include <cassert>
#include <climits>
#include <cstring>
#include <fstream>
#include <iterator>
#include <map>
#include <string>
#include <strings.h>
#include <vector>
#include "rapidxml.hpp"
#define _ASSERT assert
#define _stricmp strcasecmp
void mlog(const char*,...){}
void strcpy_safe(char* out,int size,const char* value){assert(size>0);std::strncpy(out,value,size-1);out[size-1]=0;}
void strcpy_unsafe(char* out,const char* value){std::strcpy(out,value);}
struct MZFileSystem {};
struct MXmlNode {rapidxml::xml_node<>* m_pDomNode=nullptr;void GetText(char*,int);};
struct MXmlElement:MXmlNode {
 MXmlElement(rapidxml::xml_node<>* n=nullptr){m_pDomNode=n;}
 int GetChildNodeCount(){int n=0;for(auto* c=m_pDomNode->first_node();c;c=c->next_sibling())++n;return n;}
 MXmlElement GetChildNode(int i){auto* c=m_pDomNode->first_node();while(i-- && c)c=c->next_sibling();return c;}
 template<size_t N>void GetTagName(char(&out)[N]){strcpy_safe(out,N,m_pDomNode->name());}
 bool GetAttribute(std::string* out,const char* key){auto* a=m_pDomNode->first_attribute(key);if(!a)return false;*out=a->value();return true;}
 template<size_t N>void GetContents(char(&out)[N]){GetText(out,N);}
};
struct MXmlDocument {
 rapidxml::xml_document<> Doc;std::vector<char> bytes;rapidxml::xml_node<>* Root=nullptr;
 bool LoadFromFile(const char* path,MZFileSystem*){
  std::ifstream f(path);if(!f)return false;
  bytes.assign(std::istreambuf_iterator<char>(f),{});bytes.push_back(0);
    // The fork's explicit size excludes any sentinel, matching FileBuffer.size().
    Doc.parse<rapidxml::parse_default>(bytes.data(),bytes.size()-1);
  Root=Doc.first_node("xml",0,false);return Root!=nullptr;
 }
 MXmlElement GetDocumentElement(){return Root;}
};
'''
        source += extract_body(xml_source, 'void MXmlNode::GetText(char* sOutStr, int nMaxCharNum)')
        table = original('CSCommon/Include/MStringRes.h')
        source += '''
template<class _T>struct MStringRes {
 std::map<_T,std::string> m_StringMap;
 std::string m_strTOK_TAG="STR",m_strTOK_ATTR="id";
'''
        source += extract_body(table, 'bool Initialize(const char* pszFileName, const int nLangID, MZFileSystem *pfs = 0)')
        source += extract_body(table, 'const char* GetStr( const _T& code )')
        source += r'''
};
int main(int argc,char** argv){
 assert(argc>1);int emptyMessages=0;
 for(int i=1;i<argc;++i){
  MStringRes<std::string> table;assert(table.Initialize(argv[i],0));
  MXmlDocument xml;assert(xml.LoadFromFile(argv[i],nullptr));
  for(auto* e=xml.Root->first_node();e;e=e->next_sibling()){
   auto* id=e->first_attribute("id");if(!id)continue;
   assert(e->value()!=nullptr);
   char buffer[512];std::memset(buffer,'X',sizeof(buffer));
   MXmlNode{e}.GetText(buffer,sizeof(buffer));
   assert(std::strcmp(buffer,e->value())==0);
   assert(std::strcmp(table.GetStr(id->value()),e->value())==0);
   if(std::strcmp(e->name(),"MSG")==0 && e->value()[0]==0)++emptyMessages;
  }
 }
 assert(emptyMessages>=10);
}
'''
        paths = [self.output / p for p in self.files if p.endswith(('messages.xml', 'strings.xml', 'cserror.xml'))]
        run_fixture(source, paths)

    def test_hud_art_only_changes_identified_alpha_pixels(self):
        old = (DATA / cosmetics.HUD_ART).read_bytes()
        new = (self.output / cosmetics.HUD_ART).read_bytes()
        self.assertEqual(old[:128], new[:128])
        self.assertNotEqual(old, new)
        for block in range(128, len(old), 16):
            self.assertEqual(old[block + 8:block + 16], new[block + 8:block + 16])
        for y in range(256):
            for x in range(512):
                block = 128 + ((y // 4) * 128 + x // 4) * 16
                pixel = (y % 4) * 4 + x % 4
                at, shift = block + pixel // 2, 4 * (pixel % 2)
                erased = any(a <= x < c and b <= y < d for a, b, c, d in cosmetics.HUD_ERASE_RECTS)
                self.assertEqual((new[at] >> shift) & 15, 0 if erased else (old[at] >> shift) & 15)

    def test_idempotent_output_and_untouched_pinned_data(self):
        before = {p: (self.output / p).read_bytes() for p in self.files}
        self.assertEqual(cosmetics.install(DATA, self.output), self.files)
        self.assertEqual(before, {p: (self.output / p).read_bytes() for p in self.files})
        self.assertEqual(self.before, {p: hashlib.sha256(p.read_bytes()).digest() for p in self.input_paths})

    def test_rejects_original_runtime_and_symlink_destinations(self):
        for output in (DATA, DATA / 'overlay', DATA.parent, self.output / 'reference-runtime'):
            with self.assertRaises(ValueError):
                cosmetics.install(DATA, output)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / 'client').symlink_to(DATA / 'client', target_is_directory=True)
            with self.assertRaises(ValueError):
                cosmetics.install(DATA, output)


if __name__ == '__main__':
    unittest.main()