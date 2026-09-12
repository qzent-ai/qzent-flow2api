import types
import unittest

from src.core.model_resolver import resolve_model_name
from src.services.generation_handler import MODEL_CONFIG


class OmniDurationModelConfigTests(unittest.TestCase):
    """Omni Flash (abra) 4/6/8/10 秒档位的 MODEL_CONFIG 配置校验。"""

    def _assert_omni_entry(
        self,
        config_key: str,
        *,
        t2v_key: str,
        r2v_key: str,
        duration: int,
        aspect_ratio: str,
    ):
        cfg = MODEL_CONFIG[config_key]

        self.assertEqual(cfg["type"], "video")
        self.assertEqual(cfg["video_type"], "omni")
        self.assertEqual(cfg["model_key"], t2v_key)
        self.assertEqual(cfg["reference_model_key"], r2v_key)
        self.assertEqual(cfg["reference_duration"], duration)
        self.assertEqual(cfg["aspect_ratio"], aspect_ratio)
        self.assertTrue(cfg["supports_images"])
        self.assertEqual(cfg["min_images"], 0)
        self.assertEqual(cfg["max_images"], 3)
        self.assertTrue(cfg["use_v2_model_config"])
        self.assertFalse(cfg["allow_tier_upgrade"])
        self.assertEqual(cfg["reference_model_display_name"], "Omni Flash")

    def test_existing_omni_8s_entries_unchanged(self):
        self._assert_omni_entry(
            "omni",
            t2v_key="abra_t2v_8s",
            r2v_key="abra_r2v_8s",
            duration=8,
            aspect_ratio="VIDEO_ASPECT_RATIO_LANDSCAPE",
        )
        self._assert_omni_entry(
            "omni_portrait",
            t2v_key="abra_t2v_8s",
            r2v_key="abra_r2v_8s",
            duration=8,
            aspect_ratio="VIDEO_ASPECT_RATIO_PORTRAIT",
        )

    def test_omni_4s_landscape(self):
        self._assert_omni_entry(
            "omni_4s",
            t2v_key="abra_t2v_4s",
            r2v_key="abra_r2v_4s",
            duration=4,
            aspect_ratio="VIDEO_ASPECT_RATIO_LANDSCAPE",
        )

    def test_omni_6s_landscape(self):
        self._assert_omni_entry(
            "omni_6s",
            t2v_key="abra_t2v_6s",
            r2v_key="abra_r2v_6s",
            duration=6,
            aspect_ratio="VIDEO_ASPECT_RATIO_LANDSCAPE",
        )

    def test_omni_10s_landscape(self):
        self._assert_omni_entry(
            "omni_10s",
            t2v_key="abra_t2v_10s",
            r2v_key="abra_r2v_10s",
            duration=10,
            aspect_ratio="VIDEO_ASPECT_RATIO_LANDSCAPE",
        )

    def test_omni_4s_portrait(self):
        self._assert_omni_entry(
            "omni_portrait_4s",
            t2v_key="abra_t2v_4s",
            r2v_key="abra_r2v_4s",
            duration=4,
            aspect_ratio="VIDEO_ASPECT_RATIO_PORTRAIT",
        )

    def test_omni_6s_portrait(self):
        self._assert_omni_entry(
            "omni_portrait_6s",
            t2v_key="abra_t2v_6s",
            r2v_key="abra_r2v_6s",
            duration=6,
            aspect_ratio="VIDEO_ASPECT_RATIO_PORTRAIT",
        )

    def test_omni_10s_portrait(self):
        self._assert_omni_entry(
            "omni_portrait_10s",
            t2v_key="abra_t2v_10s",
            r2v_key="abra_r2v_10s",
            duration=10,
            aspect_ratio="VIDEO_ASPECT_RATIO_PORTRAIT",
        )


class OmniDurationModelResolverTests(unittest.TestCase):
    """omni_Xs 别名族按 aspectRatio 解析到横/竖屏变体。"""

    def _resolve(self, model: str, aspect_ratio: str = None) -> str:
        generation_config = (
            types.SimpleNamespace(aspectRatio=aspect_ratio) if aspect_ratio else None
        )
        request = types.SimpleNamespace(generationConfig=generation_config)
        return resolve_model_name(model, request=request, model_config=MODEL_CONFIG)

    def test_resolve_omni_4s_alias(self):
        self.assertEqual(self._resolve("omni_4s", "landscape"), "omni_4s")
        self.assertEqual(self._resolve("omni_4s", "portrait"), "omni_portrait_4s")

    def test_resolve_omni_6s_alias(self):
        self.assertEqual(self._resolve("omni_6s", "landscape"), "omni_6s")
        self.assertEqual(self._resolve("omni_6s", "portrait"), "omni_portrait_6s")

    def test_resolve_omni_10s_alias(self):
        self.assertEqual(self._resolve("omni_10s", "landscape"), "omni_10s")
        self.assertEqual(self._resolve("omni_10s", "portrait"), "omni_portrait_10s")

    def test_resolve_omni_duration_alias_defaults_to_landscape(self):
        self.assertEqual(self._resolve("omni_4s"), "omni_4s")
        self.assertEqual(self._resolve("omni_6s"), "omni_6s")
        self.assertEqual(self._resolve("omni_10s"), "omni_10s")

    def test_resolve_base_omni_alias_still_targets_8s(self):
        self.assertEqual(self._resolve("omni", "landscape"), "omni")
        self.assertEqual(self._resolve("omni", "portrait"), "omni_portrait")

    def test_concrete_duration_keys_resolve_to_themselves(self):
        for key in (
            "omni_4s",
            "omni_6s",
            "omni_10s",
            "omni_portrait_4s",
            "omni_portrait_6s",
            "omni_portrait_10s",
        ):
            self.assertEqual(self._resolve(key), key)


if __name__ == "__main__":
    unittest.main()
