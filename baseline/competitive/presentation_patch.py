"""Controls, split Rank/ELO, no progression display, and melee HIT feedback."""
import re
try:
    from .progression_patch import block_span
except ImportError:
    from progression_patch import block_span

FILES=['Gunz/ZGameInterface.cpp','Gunz/ZCombatInterface.cpp','Gunz/ZGame.cpp',
       'Gunz/ZGameClient_Command.cpp','CSCommon/Source/MSharedCommandTable.cpp']


def changes(relative,text):
    def replace(old,new,count=1):
        nonlocal text
        if text.count(old)!=count:raise ValueError(f'{relative}: expected {count}: {old[:100]!r}, got {text.count(old)}')
        text=text.replace(old,new)
    def body(signature,new):
        nonlocal text
        a,b=block_span(text,signature);text=text[:a]+'{\n'+new+'\n}'+text[b:]
    def section(signature,edit):
        nonlocal text
        a,b=block_span(text,signature);text=text[:a]+edit(text[a:b])+text[b:]
    if relative=='Gunz/ZGameInterface.cpp':
        replace('#include "stdafx.h"','#include "stdafx.h"\n#include "presentation.hpp"')
        anchor='if (nType == ZCWT_PREV || nType == ZCWT_NEXT)'
        a,b=block_span(text,anchor)
        text=text[:a]+'''{
		bWheel = true;
		bool owned[3]{};
		for(int i=0;i<3;++i){
			auto* item=pChar->GetItems()->GetItem(MMatchCharItemParts(int(MMCIP_MELEE)+i));
			owned[i]=item && !item->IsEmpty() && item->GetDesc();
		}
		const int selected=int(pChar->GetItems()->GetSelectedWeaponParts())-int(MMCIP_MELEE);
		const int next=competitive::cycleMainWeapon(selected,nType==ZCWT_PREV,owned);
		if(next<0)return;
		nParts=int(MMCIP_MELEE)+next;
	}'''+text[b:]
    elif relative=='Gunz/ZCombatInterface.cpp':
        replace('TextRelative(pDC, .455f, y, "ELO");','TextRelative(pDC, .435f, y, "ELO");\n\tTextRelative(pDC, .505f, y, "Rank");')
        replace('int(.165f*MGetWorkspaceWidth())','int(.145f*MGetWorkspaceWidth())')
        replace('auto ratingText = CompetitiveText(pItem->uidUID);\n\t\tTextRelative(pDC,.455f,texty,ratingText.c_str());',
                'auto eloText = CompetitiveEloText(pItem->uidUID);\n\t\tTextRelative(pDC,.435f,texty,eloText.c_str());\n'
                '\t\tauto rankText = CompetitiveRankText(pItem->uidUID);\n\t\tTextRelative(pDC,.505f,texty,rankText.c_str());')
        replace('''	else
	{
		x = ITEM_XPOS[2] - .01f;	// Exp
		TextRelative(pDC,x,y, ZMsg(MSG_WORD_EXP));
	}''','')
        replace('''			x=ITEM_XPOS[2];
			sprintf_safe(szText,"%d",pItem->nExp);
			TextRelative(pDC,x,texty,szText,true);
''','')
        replace('''	if( a->nExp > b->nExp) return true;
	if( a->nExp < b->nExp) return false;
''','')
        replace('sprintf_safe(buffer, "%d  %s", pCharacter->GetProperty()->nLevel, pCharacter->GetProperty()->szName);',
                'sprintf_safe(buffer, "%s", pCharacter->GetProperty()->szName);')
        text,n=re.subn(r'sprintf_safe\( charName\[ ([012])\], "%s%d  %s", ZMsg\( MSG_CHARINFO_LEVELMARKER\),\s*pCharacter->GetProperty\(\)->nLevel, pCharacter->GetUserName\(\)\);',
                       r'sprintf_safe( charName[ \1], "%s", pCharacter->GetUserName());',text)
        if n!=4:raise ValueError('Duel name progression anchors changed')
        text,n=re.subn(r'sprintf_safe\(pItem->szName,\s*"--%s  %s", ZMsg\(MSG_CHARINFO_LEVELMARKER\), pCharacter->GetUserName\(\)\);',
                       'sprintf_safe(pItem->szName,"%s",pCharacter->GetUserName());',text)
        if n!=1:raise ValueError('Admin name anchors changed')
        replace('sprintf_safe(pItem->szName,"%d%s %s",pCharacter->GetProperty()->nLevel, ZMsg(MSG_CHARINFO_LEVELMARKER), pCharacter->GetUserName());',
                'sprintf_safe(pItem->szName,"%s",pCharacter->GetUserName());')
        replace('pItem->nScore = pCharacter->GetStatus()->nExp;','pItem->nScore = pCharacter->GetStatus()->nKills; // Results sort by kills, not XP.')
        replace('"[Level %d / %d]"','"[Weapon %d / %d]"')
        replace('strcpy_safe( szFileName, "interface/loadable/rstbg_quest.jpg");',
            'strcpy_safe( szFileName, "interface/loadable/rstbg_deathmatch.jpg"); // No baked EXP/Bounty labels.')
        replace('sprintf_safe(szText, "%s (%s %d)", szText, ZMsg(MSG_CHARINFO_LEVELMARKER),\n\t\t\t\tZGetQuest()->GetGameInfo()->GetQuestLevel());',
            '// Map name has no progression suffix.')
    elif relative=='Gunz/ZGame.cpp':
        replace('#include "client.hpp"','#include "client.hpp"\n#include "presentation.hpp"')
        replace('CompetitiveDamage().clear();','CompetitiveDamage().clear();\n\tClearCompetitiveGBucksRewards();')
        def dead(s):
            start=s.index('\n\tint nAttackerExp');end=s.index('\n\tif(pAttacker)',start)
            s=s[:start]+s[end:]
            s=s.replace('\n\t\tpAttackerCS->AddExp(nAttackerExp);','').replace('\n\t\tpVictimCS->AddExp(nVictimExp);','')
            start=s.index('\n\tif(bSuicide &&');end=s.index('\n\tm_Match.AddRoundKills();',start)
            return s[:start]+s[end:]
        signature=re.search(r'void ZGame::OnPeerDead\([^)]*\)',text).group(0)
        section(signature,dead)
        body('void ZGame::OnReceiveTeamBonus(const MUID& uidChar, const u32 nExpArg)',
             '\t// Compatibility packet only. No EXP mutation or notification.')
        def melee(s,target,damage,after):
            s=s.replace('{','{\n\tcompetitive::MeleeFeedback meleeFeedback;',1)
            anchor=f'\t\t{target}->OnDamaged('
            if s.count(anchor)!=1:raise ValueError('Melee damage anchor')
            before=f'''\t\tauto* feedbackTarget=MDynamicCast(ZCharacter,{target});
		meleeFeedback.add({damage},pOwner==m_pMyCharacter,IsReplay(),
			ZGetGameClient()->GetMatchStageSetting()->GetNetcode()==NetcodeType::ServerBased,
			!{target}->IsDead(),{target}->IsVisible(),feedbackTarget && feedbackTarget->isInvincible());
'''
            s=s.replace(anchor,before+anchor)
            if s.count(after)!=1:raise ValueError('Melee aggregate anchor')
            return s.replace(after,'\n\tCompetitiveHit(meleeFeedback.total);\n'+after)
        section('void ZGame::OnPeerShot_Melee(const MUID& uidOwner, float fShotTime)',
                lambda s:melee(s,'pTar','fActualDamage','\n\tif (!HitEnemy)'))
        section('void ZGame::OnPeerSlash(ZCharacter *pOwner, const rvector &pos, const rvector &dir, int Type)',
                lambda s:melee(s,'pTarget','fDamage','\n\tif (!bPlayerHit)'))
        # Massive only damages the local victim in upstream P2P. Evaluate the
        # shooter's contacts for presentation, but never add damage/effects there.
        def massive(s):
            s=s.replace('{','{\n\tcompetitive::MeleeFeedback meleeFeedback;',1)
            s=s.replace('ZObject *pVictim = it.second;','ZObject *pVictim = it.second;\n\t\tif (pVictim == pOwner) continue; // A missed massive must not count self.')
            old='''		if ((pOwner == m_pMyCharacter || pVictim != m_pMyCharacter)
			&& (!pVictim->IsNPC() || !static_cast<ZActor*>(pVictim)->IsMyControl()))
			continue;'''
            if old not in s:raise ValueError('Massive ownership anchor')
            s=s.replace(old,'''\t\tconst bool applyDamage = !((pOwner == m_pMyCharacter || pVictim != m_pMyCharacter)
			&& (!pVictim->IsNPC() || !static_cast<ZActor*>(pVictim)->IsMyControl()));
		if (!applyDamage && pOwner != m_pMyCharacter) continue;''')
            s=s.replace('\t\t\trvector addVel = TargetPos - pos;','\t\t\tif (!applyDamage) continue;\n\t\t\trvector addVel = TargetPos - pos;')
            s=s.replace('\t\tif (!EnchantType)','\t\tif (applyDamage && !EnchantType)').replace('\t\telse\n\t\t{\n\t\t\tZGetEffectManager()->AddSwordEnchantEffect','\t\telse if (applyDamage)\n\t\t{\n\t\t\tZGetEffectManager()->AddSwordEnchantEffect')
            anchor='\t\t// Stop dash locks'
            s=s.replace(anchor,'''\t\tauto* feedbackTarget=MDynamicCast(ZCharacter,pVictim);
		meleeFeedback.add(float(damage),pOwner==m_pMyCharacter,IsReplay(),
			ZGetGameClient()->GetMatchStageSetting()->GetNetcode()==NetcodeType::ServerBased,
			!pVictim->IsDead(),pVictim->IsVisible(),feedbackTarget && feedbackTarget->isInvincible());
		if (!applyDamage) continue;
'''+anchor)
            return s[:-1]+'\tCompetitiveHit(meleeFeedback.total);\n}'
        section('void ZGame::OnPeerMassive(ZCharacter *pOwner, const rvector &pos, const rvector &dir)',massive)
    elif relative=='Gunz/ZGameClient_Command.cpp':
        replace('bool ZGameClient::OnCommand(MCommand* pCommand)\n{','''bool ZGameClient::OnCommand(MCommand* pCommand)
{
	if (pCommand->GetID() == MC_MATCH_GBUCKS_REWARD) {
		if (pCommand->GetSenderUID() != GetServerUID()) return false;
		int amount=0,completion=0;
		if (!pCommand->GetParameter(&amount,0,MPT_INT) || !pCommand->GetParameter(&completion,1,MPT_INT) || (completion!=0 && completion!=1)) return false;
		return AddCompetitiveGBucksReward(amount,completion==1,GetGlobalTimeMS());
	}''')
    elif relative=='CSCommon/Source/MSharedCommandTable.cpp':
        replace('\t// Custom commands','\tC(MC_MATCH_GBUCKS_REWARD, "Match.GBucksReward", "Committed currency reward", MCDT_MACHINE2MACHINE);\n\t\tP(MPT_INT, "Amount");\n\t\tP(MPT_INT, "Completion");\n\n\t// Custom commands')
    else:raise ValueError('Unknown presentation patch: '+relative)
    return text