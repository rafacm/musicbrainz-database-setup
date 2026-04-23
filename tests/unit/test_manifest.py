from musicbrainz_database_setup.sql import manifest


def test_archives_for_core_default():
    assert manifest.archives_for(("core",)) == ["mbdump.tar.bz2"]


def test_archives_for_multiple_modules_preserves_order():
    assert manifest.archives_for(("core", "derived", "cover-art")) == [
        "mbdump.tar.bz2",
        "mbdump-derived.tar.bz2",
        "mbdump-cover-art-archive.tar.bz2",
    ]


def test_required_schemas_dedupes_core_modules():
    # core, derived, editor all share the musicbrainz schema; cover-art adds another.
    schemas = manifest.required_schemas(("core", "derived", "editor", "cover-art"))
    assert schemas == ["musicbrainz", "cover_art_archive"]


def test_pre_import_includes_core_ddl():
    files = manifest.pre_import_files(("core",))
    paths = [f.repo_path for f in files]
    assert paths == [
        "admin/sql/Extensions.sql",
        "admin/sql/CreateCollations.sql",
        "admin/sql/CreateSearchConfiguration.sql",
        "admin/sql/CreateTypes.sql",
        "admin/sql/CreateTables.sql",
    ]


def test_pre_import_adds_module_subdir_for_cover_art():
    files = manifest.pre_import_files(("core", "cover-art"))
    paths = [f.repo_path for f in files]
    assert paths[-1] == "admin/sql/caa/CreateTables.sql"


def test_post_import_order_matches_initdb_pl():
    files = manifest.post_import_files(("core",))
    paths = [f.repo_path for f in files]
    assert paths == [
        "admin/sql/CreatePrimaryKeys.sql",
        "admin/sql/CreateFunctions.sql",
        "admin/sql/CreateIndexes.sql",
        "admin/sql/CreateFKConstraints.sql",
        "admin/sql/CreateConstraints.sql",
        "admin/sql/SetSequences.sql",
        "admin/sql/CreateViews.sql",
        "admin/sql/CreateTriggers.sql",
    ]
