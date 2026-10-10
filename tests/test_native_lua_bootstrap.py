"""Static canonical helper profiles require no Lua execution or CE input."""
import hashlib
import unittest

from ct2trainer.native.lua_bootstrap import (
    LuaBootstrapError, MAX_SOURCE_BYTES, PROFILE, SCHEMA,
    prepare_lua_bootstrap, validate_lua_bootstrap,
)


class LuaBootstrapProfileTests(unittest.TestCase):
    def test_exact_source_unicode_line_endings_and_utf8_hash_are_retained(self):
        source = '-- Grüße\r\nfunction helper() return "α" end\r'
        profile = prepare_lua_bootstrap(source)
        self.assertEqual(profile, {"schema": SCHEMA, "profile": PROFILE, "source": source,
                                   "source_sha256": hashlib.sha256(source.encode()).hexdigest()})
        self.assertEqual(validate_lua_bootstrap(profile), profile)
        self.assertIsNot(validate_lua_bootstrap(profile), profile)

    def test_preparation_is_static_even_for_unsupported_top_level_actions(self):
        source = 'registerCustomTypeLua("test", 4, nil, nil); writeInteger(4096, 1)'
        self.assertEqual(prepare_lua_bootstrap(source)["source"], source)

    def test_empty_source_is_an_explicit_valid_noop_profile(self):
        profile = prepare_lua_bootstrap("")
        self.assertEqual(validate_lua_bootstrap(profile), profile)

    def test_size_limit_counts_utf8_bytes_and_rejects_invalid_unicode(self):
        self.assertEqual(len(prepare_lua_bootstrap("x" * MAX_SOURCE_BYTES)["source"]), MAX_SOURCE_BYTES)
        for source in ("x" * (MAX_SOURCE_BYTES + 1), "α" * (MAX_SOURCE_BYTES // 2 + 1), "\ud800", None, b"x", True):
            with self.subTest(source_type=type(source)):
                with self.assertRaises(LuaBootstrapError):
                    prepare_lua_bootstrap(source)

    def test_changed_source_hash_unknown_versions_and_extra_fields_fail_closed(self):
        profile = prepare_lua_bootstrap("function helper() return 4 end")
        forged = [dict(profile, source="function helper() return 5 end"), dict(profile, source_sha256="0" * 64),
                  dict(profile, source_sha256=profile["source_sha256"].upper()), dict(profile, schema="future"),
                  dict(profile, profile="permissive"), dict(profile, executable=True), dict(profile, source_sha256=True),
                  {}, None, [profile]]
        for candidate in forged:
            with self.subTest(candidate=candidate):
                with self.assertRaises(LuaBootstrapError):
                    validate_lua_bootstrap(candidate)


if __name__ == "__main__":
    unittest.main()
