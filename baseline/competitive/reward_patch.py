"""Exact stage-only GBucks HUD patch; compose after progression/presentation.

Main integration owns patch composition, client server-message dispatch/cache,
and CMake generation. This module never writes or reads runtime game state.
"""
try:
    from .progression_patch import block_span
except ImportError:
    from progression_patch import block_span


FILES = ['Gunz/ZScreenEffectManager.h', 'Gunz/ZScreenEffectManager.cpp']


def changes(relative, text):
    if 'm_pGBucksRewardTexture' in text:
        raise ValueError(f'{relative}: reward HUD already patched')

    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError(f'{relative}: expected one reward anchor {old!r}')
        text = text.replace(old, new)

    if relative == FILES[0]:
        replace('\tvoid DrawDamageHit();', '\tvoid DrawDamageHit();\n'
                '\tRBaseTexture* m_pGBucksRewardTexture{};\n'
                '\tvoid DrawGBucksReward();')
    elif relative == FILES[1]:
        # Require progression suppression; do not quietly compose against the
        # XP-producing original or replace that ABI entry point with currency.
        start, end = block_span(text, 'void ZScreenEffectManager::AddExpEffect(int nExp)')
        if text[start:end] != '{\n\t// No experience gain/loss graphics or score-get sound.\n}':
            raise ValueError('Reward HUD requires progression_patch suppression first')
        replace('#include "hit_hud.hpp"', '#include "hit_hud.hpp"\n#include "reward_hud.hpp"')
        replace('\tm_pDamageHitTexture = RCreateBaseTextureFromMemory(competitive::hit_art::png, sizeof(competitive::hit_art::png));',
                '\tm_pDamageHitTexture = RCreateBaseTextureFromMemory(competitive::hit_art::png, sizeof(competitive::hit_art::png));\n'
                '\tm_pGBucksRewardTexture = RCreateBaseTextureFromMemory(competitive::reward_art::png, sizeof(competitive::reward_art::png));')
        replace('void ZScreenEffectManager::Destroy()\n{', 'void ZScreenEffectManager::Destroy()\n{\n'
                '\tClearCompetitiveGBucksRewards();\n'
                '\tif (m_pGBucksRewardTexture) { RDestroyBaseTexture(m_pGBucksRewardTexture); m_pGBucksRewardTexture = nullptr; }')
        replace('\t\tDrawDamageHit();', '\t\tDrawDamageHit();\n\t\tDrawGBucksReward();')
        text += '''
void ZScreenEffectManager::DrawGBucksReward()
{
	const auto now = GetGlobalTimeMS();
	const auto* reward = CurrentCompetitiveGBucksReward(now);
	if (!reward || !m_pGBucksRewardTexture || !g_pGame || g_pGame->IsReplay()) return;
	auto* combat = ZGetGameInterface()->GetCombatInterface();
	if (!combat || combat->GetObserverMode() || combat->GetTargetCharacter() != g_pGame->m_pMyCharacter) return;
	DrawCompetitiveGBucks(RGetDevice(), m_pGBucksRewardTexture->GetTexture(), RGetScreenWidth(), RGetScreenHeight(),
		ZGetConfiguration()->GetInterfaceFix(), reward->amount, reward->completion, now - reward->at);
}
'''
    else:
        raise ValueError('Unknown reward patch: ' + relative)
    return text