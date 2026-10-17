#!/usr/bin/env python3
"""Exact, reviewable baseline patches. Applied only to the generated build stage."""
import argparse
from pathlib import Path


def changes(relative,text):
    def replace(old,new,count=1):
        nonlocal text
        if text.count(old)!=count:raise ValueError(f'{relative}: expected {count} matches for {old[:90]!r}, got {text.count(old)}')
        text=text.replace(old,new)
    if relative=='MatchServer/SQLiteDatabase.cpp':
        replace('#include "SQLiteDatabase.h"','#include "SQLiteDatabase.h"\n#include "server.hpp"')
        anchor='"DeleteFlag integer NULL)");\n}'
        replace(anchor,'"DeleteFlag integer NULL)");\n\tCompetitiveInitialize(sqlite.get());\n}')
        replace('"Values(?, ?, ?, 1, ?, ?, ?, 0, 0, "','"Values(?, ?, ?, 99, ?, ?, ?, 0, 0, "')
        start=text.index('int SQLiteDatabase::CreateCharacter(');end=text.index('bool SQLiteDatabase::DeleteCharacter(',start)
        section=text[start:end]
        if section.count('\tCommitTransaction();')!=1:raise ValueError('Character transaction boundary')
        section=section.replace('\tCommitTransaction();','\tCompetitiveGrant(sqlite.get(), static_cast<int>(CID), Sex);\n\tCommitTransaction();')
        text=text[:start]+section+text[end:]
    elif relative=='MatchServer/MMatchFormula.cpp':
        replace('int MMatchFormula::GetLevelFromExp(u32 nExp)\n{','int MMatchFormula::GetLevelFromExp(u32 nExp)\n{\n\treturn MAX_LEVEL; // Competitive server: level is not the skill ladder.')
    elif relative=='MatchServer/MMatchServer.cpp':
        replace('#include "stdafx.h"','#include "stdafx.h"\n#include "server.hpp"')
        replace('void MMatchServer::OnRun(void)\n{','void MMatchServer::OnRun(void)\n{\n\tCompetitiveBroadcast(*this);')
    elif relative=='MatchServer/MMatchObject.h':
        replace('void Heal(int Amount);','void Heal(int Amount);\n\tvoid HealCompetitivePack(int Amount, bool armor);')
    elif relative=='MatchServer/MMatchObject.cpp':
        replace('#include "stdafx.h"','#include "stdafx.h"\n#include "server.hpp"')
        replace('int HPDamage = int(Damage * PiercingRatio);','const int previousHP = max(0, HP), previousAP = max(0, AP);\n\tint HPDamage = int(Damage * PiercingRatio);')
        replace('HP -= HPDamage;\n\tAP -= APDamage;',
                'HP -= HPDamage;\n\tAP -= APDamage;\n'
                '\tCompetitiveDamageReceipt(Attacker, GetUID(), (previousHP-max(0,HP))+(previousAP-max(0,AP)));')
        text+='\nvoid MMatchObject::HealCompetitivePack(int amount, bool armor)\n{\n'
        text+='\tif (armor) AP = min(MaxAP, AP + max(0, amount));\n\telse HP = min(MaxHP, HP + max(0, amount));\n}\n'
    elif relative=='MatchServer/MMatchWorldItem.cpp':
        replace('pObj->Heal(static_cast<int>(desc_it->second->m_fAmount));',
                'if (WorldItem.nItemID == 130 || WorldItem.nItemID == 131)\n'
                '\t\t\t\tpObj->HealCompetitivePack(20, WorldItem.nItemID == 131);\n'
                '\t\t\telse pObj->Heal(static_cast<int>(desc_it->second->m_fAmount));')
    elif relative=='MatchServer/MMatchRuleDuel.h':
        replace('#include <list>','#include <list>\n#include <string>')
        replace('private:\n','private:\n\tbool ratingSettled = true;\n\tstd::string ratingEvent;\n\tvoid RateResult(const MUID& winner, const MUID& loser, const char* reason);\n')
    elif relative=='MatchServer/MMatchRuleDuel.cpp':
        replace('#include "MMatchRuleDuel.h"','#include "MMatchRuleDuel.h"\n#include "server.hpp"')
        replace('void MMatchRuleDuel::OnBegin()\n{','void MMatchRuleDuel::OnBegin()\n{\n\tratingSettled = true;')
        replace('void MMatchRuleDuel::OnRoundBegin()\n{','void MMatchRuleDuel::OnRoundBegin()\n{\n\tratingEvent = CompetitiveRoundID(GetStage()->GetUID(), GetRoundCount());\n\tratingSettled = false;')
        replace('void MMatchRuleDuel::OnRoundTimeOut()\n{','void MMatchRuleDuel::OnRoundTimeOut()\n{\n\tratingSettled = true; // Draw: no Elo win/loss.')
        replace('void MMatchRuleDuel::OnGameKill(const MUID& uidAttacker, const MUID& uidVictim)\n{',
                'void MMatchRuleDuel::OnGameKill(const MUID& uidAttacker, const MUID& uidVictim)\n{\n'
            '\t// The active survivor wins even if the death has no resolved attacker.\n'
            '\tif (uidVictim != uidChampion && uidVictim != uidChallenger) return;\n'
            '\tif (uidVictim == uidChampion)\n'
            '\t\tRateResult(uidChallenger, uidChampion, uidAttacker == uidChallenger ? "kill" : "suicide/environment");\n'
            '\telse RateResult(uidChampion, uidChallenger, uidAttacker == uidChampion ? "kill" : "suicide/environment");')
        replace('void MMatchRuleDuel::OnLeaveBattle(MUID& uidChar)\n{',
                'void MMatchRuleDuel::OnLeaveBattle(MUID& uidChar)\n{\n'
                '\tif (uidChar == uidChampion) RateResult(uidChallenger, uidChampion, "forfeit");\n'
                '\telse if (uidChar == uidChallenger) RateResult(uidChampion, uidChallenger, "forfeit");')
        text+='\nvoid MMatchRuleDuel::RateResult(const MUID& winner, const MUID& loser, const char* reason)\n{\n'
        text+='\tif (ratingSettled || GetRoundState() != MMATCH_ROUNDSTATE_PLAY || winner == MUID(0,0) || loser == MUID(0,0) || winner == loser) return;\n'
        text+='\tratingSettled = true;\n\tCompetitiveResult(GetStage(), winner, loser, ratingEvent, reason);\n}\n'
    elif relative=='CSCommon/Source/MSharedCommandTable.cpp':
        replace('#include "stdafx.h"','#include "stdafx.h"\n#include "wire.hpp"')
        replace('\t// Custom commands','\tC(MC_MATCH_DUEL_RATING, "Match.DuelRating", "Server ladder snapshot", MCDT_MACHINE2MACHINE);\n\t\tP(MPT_BLOB, "Ratings", MCPCBlobArraySize{sizeof(CompetitiveRatingWire)});\n\n\t// Custom commands')
        replace('\t// Custom commands','\tC(MC_MATCH_DAMAGE_CONFIRMATION, "Match.DamageConfirmation", "Shooter damage receipt", MCDT_MACHINE2MACHINE);\n\t\tP(MPT_INT, "Damage");\n\n\t// Custom commands')
    elif relative=='Gunz/ZGameClient_Command.cpp':
        replace('#include "stdafx.h"','#include "stdafx.h"\n#include "client.hpp"')
        replace('bool ZGameClient::OnCommand(MCommand* pCommand)\n{',
                'bool ZGameClient::OnCommand(MCommand* pCommand)\n{\n'
                '\tif (pCommand->GetID() == MC_MATCH_DUEL_RATING) {\n'
                '\t\tif (pCommand->GetSenderUID() != GetServerUID()) return false;\n'
                '\t\tCompetitiveReceive(pCommand); return true;\n\t}\n'
                '\tif (pCommand->GetID() == MC_MATCH_DAMAGE_CONFIRMATION) {\n'
                '\t\tif (pCommand->GetSenderUID() != GetServerUID()) return false;\n'
                '\t\tint amount=0; if (pCommand->GetParameter(&amount,0,MPT_INT)) CompetitiveHit(amount,true); return true;\n\t}\n'
                '\tif (pCommand->GetID() == MC_NET_ONDISCONNECT || pCommand->GetID() == MC_NET_ONCONNECT) CompetitiveClear();')
    elif relative=='Gunz/MMatchClient.cpp':
        replace('case MC_MATCH_P2P_COMMAND:\n\t{',
                'case MC_MATCH_P2P_COMMAND:\n\t{\n\t\tif (pCommand->GetSenderUID() != GetServerUID()) return false;')
    elif relative=='CSCommon/Source/MCommandCommunicator.cpp':
        replace('pCmd->m_Sender = Sender;\n\tpCmd->m_Receiver = Receiver;',
                'if (!pCmd->m_pCommandDesc->IsFlag(MCDT_PEER2PEER)) { delete pCmd; return nullptr; }\n'
                '\tpCmd->m_Sender = Sender;\n\tpCmd->m_Receiver = Receiver;')
    elif relative=='Gunz/ZTestGame.cpp':
        replace('#include "stdafx.h"','#include "stdafx.h"\n#include "competitive_config.hpp"')
        replace('info.nLevel = 0;','info.nLevel = 99;')
        replace('info.nEquipedItemDesc[MMCIP_CUSTOM2] = 30103;',
                'info.nEquipedItemDesc[MMCIP_CUSTOM2] = 30103;\n'
                '\tfor (int slot=0;slot<12;++slot) info.nEquipedItemDesc[slot] = competitive::femaleEquipment[slot];')
    elif relative=='Gunz/ZGame.cpp':
        replace('#include "stdafx.h"','#include "stdafx.h"\n#include "client.hpp"')
        replace('bool ZGame::Create(MZFileSystem *pfs, ZLoadingProgress *pLoading )\n{',
                'bool ZGame::Create(MZFileSystem *pfs, ZLoadingProgress *pLoading )\n{\n\tCompetitiveDamage().clear();')
        replace('bool PushSkip;\n};','bool PushSkip;\n\tbool DamageEligible;\n};')
        replace('ret.HitEnemy = true;\n\n\t\tif (Netcode == NetcodeType::P2PLead)',
            'ret.HitEnemy = true;\n'
            '\t\tauto* damageTarget = MDynamicCast(ZCharacter, pickinfo.pObject);\n'
            '\t\tret.DamageEligible = !damageTarget || (!damageTarget->IsDead() && damageTarget->IsVisible() && !damageTarget->isInvincible());\n\n'
            '\t\tif (Netcode == NetcodeType::P2PLead)')
        replace('if (Info.HitEnemy)\n\t{\n\t\tCheckCombo(CharOwner, Info.sdi.Target, !Info.PushSkip);',
                'if (Info.HitEnemy)\n\t{\n'
                '\t\tif (Info.DamageEligible && pOwner == m_pMyCharacter && !IsReplay() && ZGetGameClient()->GetMatchStageSetting()->GetNetcode() != NetcodeType::ServerBased)\n'
                '\t\t\tCompetitiveHit(Info.sdi.Damage);\n'
                '\t\tCheckCombo(CharOwner, Info.sdi.Target, !Info.PushSkip);')
        replace('if (!MIsDerivedFromClass(ZCharacter, New.Target))','if (!New.Target || New.Damage <= 0 || !MIsDerivedFromClass(ZCharacter, New.Target))')
        replace('auto DirGen = GetShotgunPelletDirGenerator(origdir, seed);',
                'int confirmedShotTotal = 0;\n\tauto DirGen = GetShotgunPelletDirGenerator(origdir, seed);')
        replace('HitEnemy |= Info.HitEnemy;',
                'HitEnemy |= Info.HitEnemy;\n\t\tif (Info.HitEnemy && Info.DamageEligible && Info.sdi.Damage > 0) confirmedShotTotal += Info.sdi.Damage;')
        replace('\tif (HitEnemy) {\n\t\tCheckStylishAction(pOwnerCharacter);',
                '\tif (pOwnerCharacter == m_pMyCharacter && !IsReplay() && Netcode != NetcodeType::ServerBased) CompetitiveHit(confirmedShotTotal);\n'
                '\tif (HitEnemy) {\n\t\tCheckStylishAction(pOwnerCharacter);')
    elif relative=='Gunz/ZCombatInterface.cpp':
        replace('#include "stdafx.h"','#include "stdafx.h"\n#include "client.hpp"')
        replace('const float normalXPOS[6] = {0.28f, 0.47f, 0.67f, 0.78f, 0.84f, 0.93f};',
                'const float normalXPOS[6] = {0.28f, 0.60f, 0.74f, 0.81f, 0.87f, 0.94f};')
        replace('const float clanXPOS[6]   = {0.44f, 0.24f, 0.67f, 0.76f, 0.82f, 0.91f};',
                'const float clanXPOS[6]   = {0.28f, 0.60f, 0.74f, 0.81f, 0.87f, 0.94f};')
        replace('sprintf_safe( szBuff, "%s   %s", ZMsg(MSG_CHARINFO_LEVEL), ZMsg(MSG_CHARINFO_NAME));',
                'sprintf_safe( szBuff, "%s", ZMsg(MSG_CHARINFO_NAME));')
        replace('x = ITEM_XPOS[1] + .02f;;','TextRelative(pDC, .455f, y, "ELO");\n\tx = ITEM_XPOS[1] + .02f;;')
        replace('sprintf_safe(pItem->szName, "%d%s %s", pCharacter->GetProperty()->nLevel, ZMsg(MSG_CHARINFO_LEVELMARKER), pCharacter->GetUserName());',
                'sprintf_safe(pItem->szName, "%s", pCharacter->GetUserName());')
        replace('x = ITEM_XPOS[0];\n\t\tTextRelative(pDC,x,texty,pItem->szName);',
            'x = ITEM_XPOS[0];\n\t\tstd::string nameText = pItem->szName;\n'
                '\t\twhile (!nameText.empty() && pFont->GetWidth(nameText.c_str()) > int(.165f*MGetWorkspaceWidth())) nameText.pop_back();\n'
                '\t\tTextRelative(pDC,x,texty,nameText.c_str());\n'
                '\t\tauto ratingText = CompetitiveText(pItem->uidUID);\n'
                '\t\tTextRelative(pDC,.455f,texty,ratingText.c_str());')
        # Clan-only team emblems remain in their side panel, not over ELO rows.
        replace('float clancenter = .5f*(ITEM_XPOS[0]-ITEM_XPOS[1]) + ITEM_XPOS[1];','float clancenter = .18f;')
        replace('float x1 = bClanGame ? 0.43 : 0.255;','float x1 = 0.255f;')
        replace('m_CrossHair.Draw(pDC);',
            'm_CrossHair.Draw(pDC);\n'
            '\t\tconst auto& feedback = CompetitiveDamage();\n'
            '\t\tif (feedback.visible(GetGlobalTimeMS()) && !ZGetGame()->IsReplay() && GetTargetCharacter() == g_pGame->m_pMyCharacter) {\n'
            '\t\t\tauto* savedFont = pDC->GetFont(); auto savedColor = pDC->GetColor();\n'
            '\t\t\tauto* font = GetGameFont(); pDC->SetFont(font); pDC->SetColor(MCOLOR(0xffffd079));\n'
            '\t\t\tchar damageText[64]; sprintf_safe(damageText, "%d damage%s", feedback.amount, feedback.serverConfirmed ? "" : " (P2P)");\n'
            '\t\t\tTextRelative(pDC, .5f - float(font->GetWidth(damageText)) / (2.f*MGetWorkspaceWidth()), .545f, damageText);\n'
            '\t\t\tpDC->SetFont(savedFont);pDC->SetColor(savedColor);\n\t\t}')
    else:raise ValueError('Unknown competitive patch: '+relative)
    return text


FILES=['MatchServer/SQLiteDatabase.cpp','MatchServer/MMatchFormula.cpp','MatchServer/MMatchServer.cpp',
       'MatchServer/MMatchRuleDuel.h','MatchServer/MMatchRuleDuel.cpp','CSCommon/Source/MSharedCommandTable.cpp',
    'Gunz/ZGameClient_Command.cpp','Gunz/ZCombatInterface.cpp','Gunz/ZGame.cpp',
    'MatchServer/MMatchObject.h','MatchServer/MMatchObject.cpp','MatchServer/MMatchWorldItem.cpp',
    'Gunz/MMatchClient.cpp','CSCommon/Source/MCommandCommunicator.cpp','Gunz/ZTestGame.cpp']


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);a=p.parse_args()
    outputs=[]
    for relative in FILES:
        path=a.source/relative;text=path.read_bytes().decode('latin1').replace('\r\n','\n')
        outputs.append((path,changes(relative,text)))
    for path,text in outputs:path.write_bytes(text.encode('latin1'))
    print('Applied competitive rules to build-stage sources only:',len(outputs),'files')


if __name__=='__main__':main()