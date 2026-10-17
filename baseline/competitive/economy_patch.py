#!/usr/bin/env python3
"""Backend-only GBucks patches; run AFTER existing competitive changes.

Read build/reference-source/src as latin1 with CRLF normalized; NEVER modify
that pinned tree. The owning patch_source.py writes only its build-stage copy.
Exported FILES/changes are deliberately side-effect free. --check verifies the
composition against the real source entirely in memory, with no stage writes.

INTEGRATION CONTRACT (implemented by the composed baseline):
* patch_source.py: preserve its existing FILES/changes as base, union FILES with
  this FILES, then apply base changes (if covered), then economy changes (if
  covered). Both its CLI and verifier must use that composed changes function.
* CMake: target_sources(MatchCore PRIVATE competitive/economy.cpp); append
  economy.cpp to SKIP_UNITY_BUILD_INCLUSION ON; set its COMPILE_DEFINITIONS to
  GUNZ_ECONOMY_SERVER. Link existing sqlite3 (already on MatchCore).
* server.cpp: implement the external callback declared by economy.hpp:
    void CompetitiveGBucksReward(int cid, int amount, bool completion).
    Find the CURRENT online non-bot object with that CID; if absent, drop the
    notice. Send server-only custom command 49003 to that object, amount as int
    and completion as bool (or explicitly agree to omit that field on both ends).
    Never credit/debit BP here. Client accepts only the real server sender (also
    reject peer/tunnel injection), shows '+N GBucks' for a kill, and optionally
    a completion-bonus label when completion=true. No local-death prediction and
    no popup inferred from wallet/login snapshots. The callback may throw: the
    adapter catches send failures without rolling back money or withholding ACK.
    Generated source includes economy.hpp; the adapter owns tick/lifecycle hooks.
    Do not duplicate CompetitiveBroadcast/CompetitiveInitialize calls. Schema
    init follows CompetitiveInitialize in SQLiteDatabase's constructor.
* Optional scoreboard wire: call CompetitiveGBucksEarned(stage,player) for
  committed match kill earnings (bonus excluded), after the flush/tick. Reserve
    a distinct server-only wire command; 49003 is the reward notice, NOT scoreboard.
* Wallet updates already use ResponseCharacterItemList (existing BP parameter).
    The MMatchServer.h patch exposes a narrow public CompetitiveGBucksWallet
    wrapper because the original response method is protected. Until inventory
    loads, sync updates the cache but defers the itemlist notification.
  UI agent renames Bounty to GBucks and removes Level/EXP. No XP conversion.
* Sales: main must reject selling granted starter/equipment items and validate
  the cosmetic catalogue server-side; UI filtering alone is insufficient.

REWARD/REPLAY: new accepted kills journal amount=0 with event-time eligibility.
On FIRST successful record transaction, read both server DuelRating.Elo values
(missing row=1000) in one SELECT and compute round(10+10/(1+10^((attackerElo-
victimElo)/400))), clamped 10..20; equal=15, stronger victim pays more. This is
CURRENT RECORDED ELO AT SETTLEMENT, not a guaranteed death-time Elo snapshot.
Contention/SQL/COMMIT failure retains the event; ratings may change before its
first commit. Credited and participant KillEarned atomically freeze the amount
with BP; Amount stays zero for payload identity. Replays do not query Elo or
pay/notify again. No new schema fields. Pre-upgrade queued 10..15 Amount values
retain their original promised award; new live events cannot supply an amount.
Notices are queued only for result.applied && credited>0, Kill/Finish only,
before journal ACK. Volatile EventID dedup is bound to the online object's MUID
at credit time; wallet/itemlist sync precedes sending. Disconnect/replacement
drops pending notices, and offline credits never produce later login popups.
A not-yet-credited journal event first settled while online can produce a new
notice, even after restart; a previously committed replay cannot. Send failure
or crash may lose a popup, never its committed award. Notices are consumed
before callback and are not retried (no duplicate on ambiguous send/ACK retry).

TRUST/DURABILITY: kill notifications still inherit upstream P2P death trust.
The hook validates server state/active Duel pair before OnDead, not trajectories
or damage. Not an anti-cheat rewrite. Journal + game DB need paired backups;
events retained in RAM if journal disk/lock fails can be lost on process death.
Already-journaled events survive restart. A crash is NOT natural completion.
One ordered queue intentionally stops on an unrecoverable event/overflow rather
than skipping money; investigate the server log. No ledger pruning is provided.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path


FILES = [
    'MatchServer/SQLiteDatabase.cpp', 'MatchServer/MMatchObject.h',
    'MatchServer/MMatchObject.cpp', 'MatchServer/MMatchStage.cpp',
    'MatchServer/MMatchServer_Stage.cpp', 'MatchServer/MMatchServer.cpp', 'MatchServer/MMatchServer.h',
    'MatchServer/MMatchRuleQuest.cpp',
]


def changes(relative, text):
    marker = '// GBucks backend economy patch v1\n'
    if marker in text:
        raise ValueError(f'{relative}: economy patch already applied')

    def replace(old, new, count=1):
        nonlocal text
        if text.count(old) != count:
            raise ValueError(f'{relative}: expected {count} exact anchors for {old[:90]!r}, got {text.count(old)}')
        text = text.replace(old, new)

    def body(signature, fingerprint, replacement):
        """Exact signature AND SHA256 of the whole original body, not a fuzzy edit."""
        nonlocal text
        if text.count(signature) != 1:
            raise ValueError(f'{relative}: function anchor {signature!r}')
        start = text.index('{', text.index(signature))
        depth, end = 1, start + 1
        while depth and end < len(text):
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        old = text[start:end]
        if depth or hashlib.sha256(old.encode('latin1')).hexdigest() != fingerprint:
            raise ValueError(f'{relative}: exact body changed: {signature}')
        text = text[:start] + '{\n' + replacement + '\n}' + text[end:]

    if relative == 'MatchServer/SQLiteDatabase.cpp':
        replace('#include "SQLiteDatabase.h"', '#include "SQLiteDatabase.h"\n#include "economy.hpp"')
        replace('\tCompetitiveInitialize(sqlite.get());',
                '\tCompetitiveInitialize(sqlite.get());\n\tcompetitive::economy::initialize(sqlite.get());')
        # Critical: watermark and BP must have one SELECT snapshot, not two
        # queries. Async character-load can finish after a reward commits.
        replace('"XP, BP, GameCount, KillCount, DeathCount, PlayTime, Items "',
                '"XP, BP, COALESCE((SELECT Total FROM GBucksWallet WHERE GBucksWallet.CID=Character.CID),0), "\n'
                '\t\t"GameCount, KillCount, DeathCount, PlayTime, Items "')
        replace('outCharInfo->m_nBP = stmt.Get<int>();\n\tstmt.NextColumn();',
                'outCharInfo->m_nBP = stmt.Get<int>();\n'
                '\toutCharInfo->m_nGBucksApplied = sqlite3_column_int64(stmt, 8);\n'
                '\tstmt.NextColumn(); // GBucks monotonic reward watermark (same snapshot as BP).\n'
                '\tstmt.NextColumn();')
    elif relative == 'MatchServer/MMatchObject.h':
        replace('int\t\t\t\t\tm_nBP;', 'int\t\t\t\t\tm_nBP;\n\tlong long m_nGBucksApplied = 0;')
        replace('\tvoid IncXP(int nAddedXP)\n\t{ \n'
                '\t\tm_nConnXP += nAddedXP;\n\t\tm_nXP += nAddedXP;\n'
                '\t\tm_DBCachingData.nAddedXP += nAddedXP;\n\t}\n'
                '\tvoid DecXP(int nDecXP)\n\t{ \n'
                '\t\tm_nConnXP -= nDecXP; \n\t\tm_nXP -= nDecXP; \n'
                '\t\tm_DBCachingData.nAddedXP -= nDecXP; \n\t}', '''	// XP remains a compatibility floor only; it is never GBucks.
	void IncXP(int) {}
	void DecXP(int) {}''')
    elif relative == 'MatchServer/MMatchObject.cpp':
        replace('void MMatchCharInfo::Clear()\n{',
                'void MMatchCharInfo::Clear()\n{\n\tm_nGBucksApplied = 0;')
    elif relative == 'MatchServer/MMatchStage.cpp':
        replace('#include "stdafx.h"', '#include "stdafx.h"\n#include "economy.hpp"')
        replace('void MMatchStage::OnStartGame()\n{',
                'void MMatchStage::OnStartGame()\n{\n\tCompetitiveGBucksBegin(this);')
        replace('void MMatchStage::OnFinishGame()\n{',
                'void MMatchStage::OnFinishGame()\n{\n\tCompetitiveGBucksFinish(this);')
        replace('void MMatchStage::Destroy()\n{',
                'void MMatchStage::Destroy()\n{\n\tCompetitiveGBucksDestroy(this);')
        replace('void MMatchStage::EnterBattle(MMatchObject* pObj)\n{\n\tpObj->OnEnterBattle();',
                'void MMatchStage::EnterBattle(MMatchObject* pObj)\n{\n\tpObj->OnEnterBattle();\n'
                '\tCompetitiveGBucksEnter(this, pObj);')
        replace('void MMatchStage::LeaveBattle(MMatchObject* pObj)\n{',
                'void MMatchStage::LeaveBattle(MMatchObject* pObj)\n{\n\tCompetitiveGBucksLeave(this, pObj);')
        replace('MMatchObject* pObj = i->second;\n\tpObj->SetTeam(nTeam);',
                'MMatchObject* pObj = i->second;\n'
                '\tif (nTeam == MMT_SPECTATOR) CompetitiveGBucksLeave(this, pObj);\n'
                '\tpObj->SetTeam(nTeam);')
    elif relative == 'MatchServer/MMatchServer.cpp':
        replace('#include "stdafx.h"', '#include "stdafx.h"\n#include "economy.hpp"')
        replace('\tCompetitiveBroadcast(*this);', '\tCompetitiveGBucksTick(*this);\n\tCompetitiveBroadcast(*this);')
    elif relative == 'MatchServer/MMatchServer.h':
        replace('class MMatchServer : public MServer {\npublic:',
                'class MMatchServer : public MServer {\npublic:\n'
                '\tvoid CompetitiveGBucksWallet(const MUID& player) { ResponseCharacterItemList(player); }')
    elif relative == 'MatchServer/MMatchServer_Stage.cpp':
        replace('#include "stdafx.h"', '#include "stdafx.h"\n#include "economy.hpp"')
        replace('\tpVictim->OnDead();',
                '\tCompetitiveGBucksKill(pStage, pAttacker, pVictim); // Before alive flag/duel pair changes.\n'
                '\tpVictim->OnDead();')
        body('void MMatchServer::CalcExpOnGameKill(',
             '60d7ef3763b58306e25760dbc288df08761a09e55aab77d2e636299c51d9eba9',
             '\t*poutAttackerExp = 0;\n\t*poutVictimExp = 0;')
        body('int MMatchServer::CalcBPonGameKill(',
             'a788244f3ef3eb92f3ebaa34dc569bc1a85a62c9bb163387fe0e7d6f64af352e',
             '\treturn 0; // GBucks ledger is the only kill reward path.')
        body('void MMatchServer::ProcessOnGameKill(',
             'e2e426ac406de6d124d707b2c14702bf2618c7a138c1a2aa97033cbf72e5fb29',
             '''	if (!pStage || !IsEnabledObject(pAttacker) || !IsEnabledObject(pVictim)) return;
	MUID uidStage = pStage->GetUID();
	PostGameDeadOnGameKill(uidStage, pAttacker, pVictim, 0, 0);
	if (pStage->GetStageSetting()->GetGameType() == MMATCH_GAMETYPE_TRAINING) return;
	if (pAttacker != pVictim) pAttacker->GetCharInfo()->IncKill();
	pVictim->GetCharInfo()->IncDeath();
	if (pAttacker->GetCharInfo()->GetDBCachingData()->IsRequestUpdate()) UpdateCharDBCachingData(pAttacker);
	if (pVictim->GetCharInfo()->GetDBCachingData()->IsRequestUpdate()) UpdateCharDBCachingData(pVictim);''')
        body('void MMatchServer::ProcessPlayerXPBP(',
             'd3a2d3afb80ef801bdd028ec53d2001cda633089111bde312e95ab8f34d1cc8d',
             '\t// No XP progression or legacy quest/NPC BP rewards; never convert XP.')
        body('void MMatchServer::ApplyObjectTeamBonus(',
             '682e53afbff109f969269d274461fad6d0d29790a3976dfc3ab137d64119f555',
             '\t// Team EXP and its notifications are disabled, not converted to currency.')
        body('void MMatchServer::PostGameDeadOnGameKill(',
             'a786a865930a9e2db93178ed602be7b81f833b13b4a217c6ecb1cbfc09b18428',
             '''	// Preserve death routing, but send neither XP changes nor level-percent bits.
	MCommand* pCmd = CreateCommand(MC_MATCH_GAME_DEAD, MUID(0,0));
	pCmd->AddParameter(new MCommandParameterUID(pAttacker->GetUID()));
	pCmd->AddParameter(new MCommandParameterUInt(0));
	pCmd->AddParameter(new MCommandParameterUID(pVictim->GetUID()));
	pCmd->AddParameter(new MCommandParameterUInt(0));
	RouteToBattle(uidStage, pCmd);''')
    elif relative == 'MatchServer/MMatchRuleQuest.cpp':
        replace('int nSectorXP = pScenario->nSectorXP;', 'int nSectorXP = 0; // No EXP rewards.')
        replace('int nSectorBP = pScenario->nSectorBP;', 'int nSectorBP = 0; // Only eligible PvP kills earn GBucks.')
        body('void MMatchRuleQuest::DistributeXPnBP(',
             '9a206399ffa4e06a2276fb308c87a7394a0e76aad79a92d6559cd9392227fea0',
             '\tpPlayerInfo->nXP = 0;\n\tpPlayerInfo->nBP = 0;')
    else:
        raise ValueError('Unknown economy patch: ' + relative)
    return marker + text


def check(source):
    spec = importlib.util.spec_from_file_location('gbucks_existing_patches', Path(__file__).with_name('patch_source.py'))
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    outputs = {}
    # After main composes this module, use its saved base API to avoid reapplying.
    base_files = getattr(base, 'BASE_FILES', base.FILES)
    base_changes = getattr(base, 'base_changes', base.changes)
    for relative in FILES:
        text = (source / relative).read_bytes().decode('latin1').replace('\r\n', '\n')
        if relative in base_files:
            text = base_changes(relative, text)
        outputs[relative] = changes(relative, text)
        try:
            changes(relative, outputs[relative])
        except ValueError:
            pass
        else:
            raise AssertionError(f'{relative}: duplicate patch not rejected')
    stage = outputs['MatchServer/MMatchStage.cpp']
    death = outputs['MatchServer/MMatchServer_Stage.cpp']
    assert stage.count('CompetitiveGBucksFinish(this)') == 1
    assert 'CompetitiveGBucksFinish' not in death
    assert death.index('CompetitiveGBucksKill(pStage, pAttacker, pVictim)') < death.index('pVictim->OnDead();')
    assert 'MC_MATCH_GAME_LEVEL_UP' not in death and 'MC_MATCH_GAME_TEAMBONUS' not in death
    assert 'IncBP(' not in death and 'IncXP(' not in death and 'DecXP(' not in death
    # Check the real disconnect path too, not only economy's simulated state.
    server = outputs['MatchServer/MMatchServer.cpp']
    removal = server[server.index('int MMatchServer::ObjectRemove('):server.index('MMatchObject* MMatchServer::GetObject(')]
    assert removal.index('StageLeaveBattle(') < removal.index('delete pObj;')
    assert removal.index('StageLeave(') < removal.index('delete pObj;')
    leave = stage[stage.index('void MMatchStage::LeaveBattle('):stage.index('bool MMatchStage::CheckTick(')]
    assert leave.index('CompetitiveGBucksLeave(') < leave.index('m_pRule->OnLeaveBattle(')
    finish = stage[stage.index('void MMatchStage::OnFinishGame('):stage.index('bool MMatchStage::CheckBattleEntry(')]
    assert finish.index('CompetitiveGBucksFinish(') < finish.index('StageFinishGame(')
    # Exercise the EXACT generated character query, including its correlated
    # reward watermark and column position, on a disposable in-memory database.
    import re
    import sqlite3
    database = outputs['MatchServer/SQLiteDatabase.cpp']
    query_start = database.index('bool SQLiteDatabase::GetCharInfoByAID(')
    query_start = database.index('\n\tstmt = ExecuteSQL(', query_start)
    query_end = database.index('\n\t\tCID);', query_start)
    query = ''.join(re.findall(r'"([^"\n]*)"', database[query_start:query_end]))
    with sqlite3.connect(':memory:') as db:
        db.executescript('CREATE TABLE Character(CID,Name,Level,Sex,CharNum,Hair,Face,XP,BP,GameCount,KillCount,DeathCount,PlayTime,Items);'
                         'CREATE TABLE GBucksWallet(CID,Total);'
                         "INSERT INTO Character VALUES(1,'test',99,0,0,0,0,1101991900,1234,3,4,5,6,NULL);")
        row = db.execute(query, (1,)).fetchone()
        assert row[7:11] == (1234, 0, 3, 4)
        db.execute('INSERT INTO GBucksWallet VALUES(1,2147483660)')
        row = db.execute(query, (1,)).fetchone()
        assert row[7:11] == (1234, 2147483660, 3, 4)
    print(f'PASS: {len(outputs)} real-source economy patches composed in memory; duplicate application rejected')
    print('PASS: actual disconnect/final-finish/death hook ordering and exact character-load SQL (64-bit watermark)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', required=True)
    parser.add_argument('--source', type=Path, required=True)
    check(parser.parse_args().source)