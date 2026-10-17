"""Exercise the actual competitive C++ SQLite logic and data overlays, no game launch."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import re
import sqlite3
from contextlib import closing
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'baseline/competitive'))
sys.path.insert(0,str(ROOT/'baseline'))
from data import header,install_items,CONFIG
from patch_source import changes,FILES
from runtime import backup_before_competitive


class CompetitiveTests(unittest.TestCase):
    def test_wire_ids_do_not_collide(self):
        sources=[ROOT/'build/reference-source/src'/p for p in ('CSCommon/Include/MSharedCommandTable.h','Gunz/ZCommandTable.h')]
        ids={int(n,0) for source in sources for n in re.findall(r'^\s*#define\s+\w+\s+(0x[\da-fA-F]+|\d+)',source.read_text(errors='replace'),re.M)}
        custom=[int(n) for n in re.findall(r'constexpr int \w+=(\d+)',(ROOT/'baseline/competitive/wire.hpp').read_text())]
        self.assertEqual(len(custom),len(set(custom)))
        self.assertTrue(all(0<n<65536 and n not in ids for n in custom))

    def test_exact_source_patches_and_guards(self):
        source=ROOT/'build/reference-source/src'
        for name in FILES:
            original=(source/name).read_bytes().decode('latin1').replace('\r\n','\n')
            patched=changes(name,original)
            self.assertNotEqual(original,patched,name)
            with self.assertRaises(ValueError):changes(name,'')
        duel=changes('MatchServer/MMatchRuleDuel.cpp',(source/'MatchServer/MMatchRuleDuel.cpp').read_bytes().decode('latin1'))
        self.assertIn('GetRoundState() != MMATCH_ROUNDSTATE_PLAY',duel)
        self.assertIn('ratingSettled = true; // Draw',duel)
        self.assertIn('"forfeit"',duel)
        hud=changes('Gunz/ZCombatInterface.cpp',(source/'Gunz/ZCombatInterface.cpp').read_bytes().decode('latin1'))
        self.assertIn('.455f, y, "ELO"',hud)
        self.assertIn('0.60f, 0.74f',hud) # Elo sits before Clan, not after it.
        self.assertIn('feedback.visible',hud)
        tunnel=changes('CSCommon/Source/MCommandCommunicator.cpp',(source/'CSCommon/Source/MCommandCommunicator.cpp').read_text(encoding='latin1'))
        self.assertIn('!pCmd->m_pCommandDesc->IsFlag(MCDT_PEER2PEER)',tunnel)

    def test_backup_before_migration(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);database=root/'original.sq3';backups=root/'backups'
            self.assertIsNone(backup_before_competitive(database,backups))
            self.assertFalse(database.exists())
            with closing(sqlite3.connect(database)) as db, db:
                db.execute('CREATE TABLE Character(CID INTEGER,Level INTEGER)')
                db.execute('INSERT INTO Character VALUES(42,1)')
            saved=backup_before_competitive(database,backups)
            with closing(sqlite3.connect(saved)) as db:self.assertEqual(db.execute('SELECT * FROM Character').fetchall(),[(42,1)])
            with closing(sqlite3.connect(database)) as db, db:
                db.execute('CREATE TABLE CompetitiveStarter(CID INTEGER,Version INTEGER)')
                db.execute('UPDATE Character SET Level=99')
            self.assertIsNone(backup_before_competitive(database,backups))
            self.assertEqual(len(list(backups.iterdir())),1)
            with closing(sqlite3.connect(saved)) as db:self.assertEqual(db.execute('SELECT Level FROM Character').fetchone()[0],1)

    def test_actual_duel_hooks(self):
        source=(ROOT/'build/reference-source/src/MatchServer/MMatchRuleDuel.cpp').read_bytes().decode('latin1').replace('\r\n','\n')
        patched=changes('MatchServer/MMatchRuleDuel.cpp',source)
        def prefix(signature):
            start=patched.index(signature)
            old_start=source.index(signature)+len(signature)
            tail=source[old_start:].splitlines()[1]
            # The exact inserted hook precedes the original function body.
            end=patched.index('\n'+tail+'\n',start+len(signature))
            return patched[start:end]+'\n}\n'
        hooks=''.join(prefix(s) for s in (
            'void MMatchRuleDuel::OnGameKill(const MUID& uidAttacker, const MUID& uidVictim)\n{',
            'void MMatchRuleDuel::OnLeaveBattle(MUID& uidChar)\n{',
            'void MMatchRuleDuel::OnRoundTimeOut()\n{'))
        hooks+=patched[patched.index('void MMatchRuleDuel::RateResult('):]
        harness='''
#include <string>
#include <cassert>
struct MUID {int value;MUID(int a=0,int b=0):value(a+b){} bool operator==(MUID o)const{return value==o.value;} bool operator!=(MUID o)const{return !(*this==o);} };
constexpr int MMATCH_ROUNDSTATE_PLAY=1;
int results=0,winner=0,loser=0;
void CompetitiveResult(void*,MUID w,MUID l,const std::string&,const char*){++results;winner=w.value;loser=l.value;}
struct MMatchRuleDuel {
    MUID uidChampion{1},uidChallenger{2};bool ratingSettled=false;std::string ratingEvent="event";int state=1;
    void* GetStage(){return nullptr;}int GetRoundState(){return state;}
    void RateResult(const MUID&,const MUID&,const char*);
    void OnGameKill(const MUID&,const MUID&);void OnLeaveBattle(MUID&);void OnRoundTimeOut();
};
'''+hooks+'''
int main(){
    MUID a(1),b(2),waiting(3),zero;
    MMatchRuleDuel kill;kill.OnGameKill(a,b);assert(results==1&&winner==1&&loser==2);kill.OnLeaveBattle(a);assert(results==1);
    MMatchRuleDuel suicide;suicide.OnGameKill(a,a);assert(results==2&&winner==2&&loser==1);
    MMatchRuleDuel environment;environment.OnGameKill(zero,b);environment.OnLeaveBattle(a);assert(results==3&&winner==1&&loser==2);
    MMatchRuleDuel forfeit;forfeit.OnLeaveBattle(b);forfeit.OnGameKill(a,b);assert(results==4);
    MMatchRuleDuel queued;queued.OnLeaveBattle(waiting);queued.OnGameKill(a,waiting);assert(results==4&&!queued.ratingSettled);
    MMatchRuleDuel draw;draw.OnRoundTimeOut();draw.OnLeaveBattle(a);assert(results==4);
    MMatchRuleDuel countdown;countdown.state=0;countdown.OnGameKill(a,b);countdown.OnLeaveBattle(a);assert(results==4);
    MMatchRuleDuel missing;missing.uidChampion=zero;missing.OnLeaveBattle(b);assert(results==4);
}
'''
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);(path/'hooks.cpp').write_text(harness)
            subprocess.run(['g++','-std=c++14','-Wall','-Wextra','-Werror',str(path/'hooks.cpp'),'-o',str(path/'hooks')],check=True)
            subprocess.run([str(path/'hooks')],check=True)

    def test_runtime_data_overlay(self):
        with tempfile.TemporaryDirectory() as d:
            runtime=Path(d)
            install_items(ROOT/'build/reference-data',runtime)
            client=ET.parse(runtime/'client/system/zitem.xml')
            server=ET.parse(runtime/'server/zitem.xml')
            ci={int(e.get('id')):e for e in client.getroot()};si={int(e.get('id')):e for e in server.getroot()}
            self.assertEqual(ci[25011].attrib,si[25011].attrib)
            self.assertEqual((ci[25011].get('hp'),ci[25011].get('ap')),('10','10'))
            self.assertEqual(CONFIG['rings'],[25011,25011])
            for path in (runtime/'client/system/worlditem.xml',runtime/'server/worlditem.xml'):
                entries={int(e.get('id')):e for e in ET.parse(path).getroot().iter('WORLDITEM')}
                self.assertEqual(entries[130].findtext('AMOUNT'),'20');self.assertEqual(entries[130].findtext('TYPE'),'hp')
                self.assertEqual(entries[131].findtext('AMOUNT'),'20');self.assertEqual(entries[131].findtext('TYPE'),'ap')
            install_items(ROOT/'build/reference-data',runtime)
            self.assertEqual(len([x for x in ET.parse(runtime/'client/system/zitem.xml').getroot() if x.get('id')=='25011']),1)

    def test_real_cpp_store_and_damage_logic(self):
        with tempfile.TemporaryDirectory() as d:
            temp=Path(d);(temp/'competitive_config.hpp').write_text(header(ROOT/'build/reference-data'))
            binary=temp/'competitive-tests'
            subprocess.run(['g++','-std=c++14','-Wall','-Wextra','-Werror','-I'+str(temp),'-I'+str(ROOT/'baseline/competitive'),
                            str(ROOT/'baseline/competitive/store.cpp'),str(ROOT/'baseline/competitive/tests.cpp'),'-lsqlite3','-o',str(binary)],check=True)
            subprocess.run([str(binary),str(temp/'test.sqlite')],check=True)


if __name__=='__main__':unittest.main()