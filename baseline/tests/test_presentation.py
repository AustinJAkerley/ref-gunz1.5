"""Pure controls and melee feedback plus exact final generated-source contracts."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'baseline/competitive'))
import patch_source
from progression_patch import block_span

def source(name):
    return patch_source.changes(name,(ROOT/'build/reference-source/src'/name).read_bytes().decode('latin1').replace('\r\n','\n'))

class PresentationTests(unittest.TestCase):
    def test_controls_and_melee_logic(self):
        code=r'''
#include "presentation.hpp"
#include <cassert>
int main(){
 for(int mask=0;mask<8;++mask){bool owned[3]={bool(mask&1),bool(mask&2),bool(mask&4)};
  for(int selected=-1;selected<6;++selected)for(bool prev:{false,true}){
   int n=competitive::cycleMainWeapon(selected,prev,owned);
   if(mask==0)assert(n==-1);else assert(n>=0&&n<3&&owned[n]);
  }
 }
 bool all[3]={true,true,true};assert(competitive::cycleMainWeapon(2,false,all)==0);
 assert(competitive::cycleMainWeapon(0,true,all)==2);
 assert(competitive::cycleMainWeapon(3,false,all)==0);
 assert(competitive::cycleMainWeapon(4,true,all)==2);
 bool one[3]={false,true,false};assert(competitive::cycleMainWeapon(3,true,one)==1);
 competitive::MeleeFeedback hit;
 hit.add(23,true,false,false,true,true,false);hit.add(20,true,false,false,true,true,false);assert(hit.total==43);
 hit.add(99,true,false,false,true,true,true);hit.add(99,false,false,false,true,true,false);
 hit.add(99,true,true,false,true,true,false);hit.add(99,true,false,true,true,true,false);
 hit.add(99,true,false,false,false,true,false);hit.add(99,true,false,false,true,false,false);assert(hit.total==43);
}
'''
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'test.cpp').write_text(code)
            subprocess.run(['g++','-std=c++14','-Wall','-Wextra','-Werror','-I'+str(ROOT/'baseline/competitive'),str(root/'test.cpp'),'-o',str(root/'test')],check=True)
            subprocess.run([str(root/'test')],check=True)

    def test_scroll_does_not_change_direct_custom_slots(self):
        ui=source('Gunz/ZGameInterface.cpp')
        self.assertIn('competitive::cycleMainWeapon',ui)
        self.assertIn('case ZCWT_CUSTOM1:',ui);self.assertIn('case ZCWT_CUSTOM2:',ui)
        self.assertNotIn('ItemQueue[int(MMCIP_END)',ui)

    def test_final_scoreboard_has_no_exp_and_separate_rank(self):
        ui=source('Gunz/ZCombatInterface.cpp')
        self.assertIn('CompetitiveRankText',ui);self.assertIn('CompetitiveEloText',ui)
        self.assertNotIn('MSG_CHARINFO_LEVEL',ui)
        self.assertNotIn('MSG_WORD_EXP',ui)
        self.assertNotIn('"%d",pItem->nExp',ui)
        self.assertNotIn('GetProperty()->nLevel',ui)

    def test_local_sword_feedback_does_not_duplicate_damage(self):
        game=source('Gunz/ZGame.cpp')
        for signature in ('void ZGame::OnPeerShot_Melee(const MUID& uidOwner, float fShotTime)',
                          'void ZGame::OnPeerSlash(ZCharacter *pOwner, const rvector &pos, const rvector &dir, int Type)',
                          'void ZGame::OnPeerMassive(ZCharacter *pOwner, const rvector &pos, const rvector &dir)'):
            a,b=block_span(game,signature);body=game[a:b]
            self.assertEqual(body.count('CompetitiveHit(meleeFeedback.total)'),1)
            self.assertEqual(body.count('->OnDamaged('),1)
            self.assertIn('isInvincible()',body)
            self.assertLess(body.index('IsGuardNonrecoilable'),body.index('meleeFeedback.add'))
        self.assertIn('if (!applyDamage) continue;',game)
        self.assertIn('if (pVictim == pOwner) continue; // A missed massive must not count self.',game)

    def test_reward_notice_is_server_only(self):
        commands=source('Gunz/ZGameClient_Command.cpp')
        start=commands.index('pCommand->GetID() == MC_MATCH_GBUCKS_REWARD')
        self.assertLess(commands.index('GetServerUID()',start),commands.index('AddCompetitiveGBucksReward',start))
        self.assertIn('(completion!=0 && completion!=1)',commands)

if __name__=='__main__':unittest.main()