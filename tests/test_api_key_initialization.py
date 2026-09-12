import pytest
from src.core.database import Database

@pytest.mark.asyncio
@pytest.mark.parametrize('value', [None, ''])
async def test_unconfigured_key_is_random_persisted_and_unique(tmp_path, value):
    keys = []
    for i in range(2):
        db = Database(db_path=str(tmp_path / f'{i}.db'))
        await db.init_db()
        await db.init_config_from_toml({'global': {'api_key': value}})
        key = (await db.get_admin_config()).api_key
        assert key and len(key) >= 43
        await db.init_config_from_toml({'global': {'api_key': 'replacement'}}, False)
        assert (await db.get_admin_config()).api_key == key
        keys.append(key)
    assert keys[0] != keys[1]

@pytest.mark.asyncio
async def test_explicit_key_is_preserved(tmp_path):
    db = Database(db_path=str(tmp_path / 'explicit.db'))
    await db.init_db()
    await db.init_config_from_toml({'global': {'api_key': 'explicit-test-key'}})
    assert (await db.get_admin_config()).api_key == 'explicit-test-key'

@pytest.mark.asyncio
async def test_missing_configuration_and_legacy_existing_key(tmp_path):
    db = Database(db_path=str(tmp_path / 'missing.db'))
    await db.init_db()
    await db.init_config_from_toml({})
    assert len((await db.get_admin_config()).api_key) >= 43
    await db.update_admin_config(api_key='han1234')
    await db.init_config_from_toml({}, False)
    assert (await db.get_admin_config()).api_key == 'han1234'
