"""Dialect-neutral dangerous function names for read-only SQL inspection."""

DENIED_FUNCTIONS = frozenset({
    'dblink', 'dblink_connect', 'dblink_connect_u', 'dblink_disconnect',
    'dblink_exec', 'lo_export', 'lo_import', 'lo_create', 'lo_unlink',
    'nextval', 'pg_advisory_lock', 'pg_advisory_lock_shared',
    'pg_advisory_unlock', 'pg_advisory_unlock_all',
    'pg_advisory_unlock_shared', 'pg_cancel_backend',
    'pg_create_restore_point', 'pg_export_snapshot',
    'pg_ls_archive_statusdir', 'pg_ls_dir', 'pg_ls_logdir', 'pg_ls_waldir',
    'pg_read_binary_file', 'pg_read_file', 'pg_reload_conf',
    'pg_rotate_logfile', 'pg_sleep', 'pg_stat_file', 'pg_switch_wal',
    'pg_terminate_backend', 'pg_try_advisory_lock',
    'pg_try_advisory_lock_shared', 'pg_notify', 'set_config', 'setval',
    'load_extension', 'readfile', 'writefile', 'sqlite_readfile',
    'sqlite_writefile', 'external_query',
})
