"""Reward art and exact in-memory patch contracts; no staged/live file writes."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'baseline/competitive'))
import patch_source
import progression_patch
import reward_patch


class RewardPatchTests(unittest.TestCase):
    def source(self, relative):
        path = ROOT / 'build/reference-source/src' / relative
        if not path.exists():
            self.skipTest('Pinned reference source not fetched')
        return path.read_bytes().decode('latin1').replace('\r\n', '\n')

    def composed(self, relative):
        text = self.source(relative)
        # Main owns the composition chain; exercise all available stages, even
        # if a concurrent integration adds economy/presentation changes here.
        if relative in patch_source.BASE_FILES:
            text = patch_source.base_changes(relative, text)
        modules = []
        for name in ('economy_patch', 'progression_patch', 'presentation_patch'):
            if importlib.util.find_spec(name):
                modules.append(__import__(name))
        for module in modules:
            if relative in module.FILES:
                text = module.changes(relative, text)
        return text

    def test_composition_keeps_hit_and_suppresses_progression(self):
        for relative in reward_patch.FILES:
            text = reward_patch.changes(relative, self.composed(relative))
            self.assertIn('m_pDamageHitTexture', text)
            self.assertIn('DrawGBucksReward', text)
            with self.assertRaises(ValueError):
                reward_patch.changes(relative, text)
            if relative.endswith('.cpp'):
                self.assertIn('DrawDamageHit();', text)
                self.assertIn('g_pGame->IsReplay()', text)
                self.assertIn('combat->GetObserverMode()', text)
                self.assertIn('ClearCompetitiveGBucksRewards();', text)
                begin, end = progression_patch.block_span(text, 'void ZScreenEffectManager::AddExpEffect(int nExp)')
                self.assertEqual(text[begin:end], '{\n\t// No experience gain/loss graphics or score-get sound.\n}')
                begin, end = progression_patch.block_span(text, 'void ZScreenEffectManager::DrawGBucksReward()')
                self.assertNotIn('nExp', text[begin:end])
                self.assertNotIn('PlaySound', text[begin:end])

    def test_requires_suppression_and_exact_anchors(self):
        relative = reward_patch.FILES[1]
        with self.assertRaises(ValueError):
            reward_patch.changes(relative, patch_source.changes(relative, self.source(relative)))
        with self.assertRaises(ValueError):
            reward_patch.changes(relative, self.composed(relative).replace('DrawDamageHit();', 'DrawOtherHit();'))
        with self.assertRaises(ValueError):
            reward_patch.changes('Gunz/ZGame.cpp', '')


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow required for asset tests')
class RewardArtTests(unittest.TestCase):
    def test_original_digits_plus_and_animation(self):
        import reward_art
        from PIL import Image
        data = ROOT / 'build/reference-data'
        directory = data / 'client/Interface/default/combat'
        if not directory.exists():
            self.skipTest('Pinned reference assets not fetched')
        atlas, glyphs, rects, anchor, motion, fade = reward_art.make_art(data)
        original = Image.open(directory / 'exp_num.tga.dds').convert('RGBA')
        self.assertEqual(len(glyphs), 12)
        self.assertEqual(atlas.size, (1024, 128))
        self.assertTrue(-400 < anchor[0] < -350 and 200 < anchor[1] < 210)
        self.assertEqual(motion[0], (0, 1))
        self.assertEqual(motion[-1], (4800, 3))
        self.assertEqual(fade[-1], (0, 4800))
        for i in range(11):
            suffix, name = (f'num_{i}', f'exp_num_{i}') if i < 10 else ('+', 'exp +')
            _, uv, _ = reward_art.mesh(directory / f'ef_exp_{suffix}.elu', name)
            x, y, w, h = rects[i]
            import math
            bx, by = max(0, math.floor(uv[0] * 256)), max(0, math.floor(uv[1] * 64))
            self.assertEqual(atlas.crop((x, y, x + w, y + h)).tobytes(),
                             original.crop((bx, by, bx + w, by + h)).tobytes(), 'original pixels, not typeset numbers')
        self.assertIn('namespace reward_art', reward_art.header(data))
        self.assertEqual(reward_art.header(data), reward_art.header(data), 'deterministic build art')


if __name__ == '__main__':
    unittest.main()