// Administration: backups and the update notice (admin only).

class BackupItem {
  final String name;
  final int size;
  final String kind; // manual | auto | safety | uploaded | other
  final DateTime? createdAt;
  final String? hubVersion;
  final bool includesKeys;
  final bool valid;

  const BackupItem({
    required this.name,
    this.size = 0,
    this.kind = 'other',
    this.createdAt,
    this.hubVersion,
    this.includesKeys = false,
    this.valid = true,
  });

  factory BackupItem.fromJson(Map<String, dynamic> j) => BackupItem(
        name: j['name'] as String,
        size: (j['size'] as num?)?.toInt() ?? 0,
        kind: (j['kind'] as String?) ?? 'other',
        createdAt: DateTime.tryParse((j['created_at'] as String?) ?? ''),
        hubVersion: j['hub_version'] as String?,
        includesKeys: j['includes_keys'] == true,
        valid: j['valid'] != false,
      );
}

class BackupInfo {
  final DateTime? lastAt;
  final bool? lastOk;
  final String? lastError;
  final DateTime? lastRestoreAt;
  final bool auto;
  final int keep;
  final String autoTime;
  final String dialect;
  final String version;
  final List<BackupItem> backups;

  const BackupInfo({
    this.lastAt,
    this.lastOk,
    this.lastError,
    this.lastRestoreAt,
    this.auto = false,
    this.keep = 7,
    this.autoTime = '03:30',
    this.dialect = '',
    this.version = '',
    this.backups = const [],
  });

  factory BackupInfo.fromJson(Map<String, dynamic> j) {
    final last = (j['last'] as Map?)?.cast<String, dynamic>() ?? const {};
    return BackupInfo(
      lastAt: DateTime.tryParse((last['at'] as String?) ?? ''),
      lastOk: last['ok'] as bool?,
      lastError: last['error'] as String?,
      lastRestoreAt: DateTime.tryParse((j['last_restore_at'] as String?) ?? ''),
      auto: j['auto'] == true,
      keep: (j['keep'] as num?)?.toInt() ?? 7,
      autoTime: (j['auto_time'] as String?) ?? '03:30',
      dialect: (j['dialect'] as String?) ?? '',
      version: (j['version'] as String?) ?? '',
      backups: ((j['backups'] as List?) ?? const []).whereType<Map<String, dynamic>>().map(BackupItem.fromJson).toList(),
    );
  }
}

/// Answer of a backup or restore action: `ok`, or a stable `code` plus the server's English `message`.
class BackupResult {
  final bool ok;
  final String? code;
  final String? message;
  final bool restartRequired;
  final String? safetyBackup;
  final List<String> warnings;

  const BackupResult({
    this.ok = false,
    this.code,
    this.message,
    this.restartRequired = false,
    this.safetyBackup,
    this.warnings = const [],
  });

  factory BackupResult.fromJson(Map<String, dynamic> j) => BackupResult(
        ok: j['ok'] == true,
        code: j['code'] as String?,
        message: j['message'] as String?,
        restartRequired: j['restart_required'] == true,
        safetyBackup: j['safety_backup'] as String?,
        warnings: ((j['warnings'] as List?) ?? const []).map((e) => '$e').toList(),
      );
}
