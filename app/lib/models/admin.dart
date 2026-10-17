// Verwaltung: Systemübersicht, Familie, Haus-Auswahl, Protokoll (nur Admins).

class PluginHealth {
  final String id;
  final String name;
  final bool active;
  final bool configured;
  final List<String> missing;
  final String status; // ok | error | off | unknown
  final String message;
  final int? latencyMs;

  const PluginHealth({
    required this.id,
    required this.name,
    this.active = false,
    this.configured = false,
    this.missing = const [],
    this.status = 'unknown',
    this.message = '',
    this.latencyMs,
  });

  factory PluginHealth.fromJson(Map<String, dynamic> j) {
    final h = (j['health'] as Map?)?.cast<String, dynamic>() ?? const {};
    return PluginHealth(
      id: j['id'] as String,
      name: (j['name'] as String?) ?? j['id'] as String,
      active: j['active'] == true,
      configured: j['configured'] == true,
      missing: ((j['missing'] as List?) ?? const []).map((e) => '$e').toList(),
      status: (h['status'] as String?) ?? 'unknown',
      message: (h['message'] as String?) ?? '',
      latencyMs: h['latency_ms'] as int?,
    );
  }
}

class AdminOverview {
  final String version;
  final List<PluginHealth> plugins;
  final bool fcm;
  final bool webpush;
  final int fcmDevices;
  final int webpushDevices;
  final int activeUsers;

  const AdminOverview({
    required this.version,
    this.plugins = const [],
    this.fcm = false,
    this.webpush = false,
    this.fcmDevices = 0,
    this.webpushDevices = 0,
    this.activeUsers = 0,
  });

  int get problems => plugins.where((p) => p.status == 'error').length;

  factory AdminOverview.fromJson(Map<String, dynamic> j) {
    final push = (j['push'] as Map?)?.cast<String, dynamic>() ?? const {};
    final devices = (push['devices'] as Map?)?.cast<String, dynamic>() ?? const {};
    return AdminOverview(
      version: ((j['server'] as Map?)?['version'] as String?) ?? '?',
      plugins: ((j['plugins'] as List?) ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(PluginHealth.fromJson)
          .toList(),
      fcm: push['fcm'] == true,
      webpush: push['webpush'] == true,
      fcmDevices: (devices['fcm'] as int?) ?? 0,
      webpushDevices: (devices['webpush'] as int?) ?? 0,
      activeUsers: ((j['users'] as Map?)?['active'] as int?) ?? 0,
    );
  }
}

const roleLabels = {'admin': 'Admin', 'partner': 'Partner', 'child': 'Kind', 'guest': 'Gast'};
const linkLabels = {'nextcloud': 'Nextcloud', 'habitica': 'Habitica', 'paperless': 'Paperless', 'seerr': 'Seerr'};

class AdminUser {
  final int id;
  final String username;
  final String displayName;
  final String? email;
  final String role;
  final bool active;
  final DateTime? lastLogin;
  final String? avatarColor;
  final String? avatarUrl;
  final int devices;
  final Map<String, bool?> links;

  const AdminUser({
    required this.id,
    required this.username,
    required this.displayName,
    this.email,
    this.role = 'partner',
    this.active = true,
    this.lastLogin,
    this.avatarColor,
    this.avatarUrl,
    this.devices = 0,
    this.links = const {},
  });

  factory AdminUser.fromJson(Map<String, dynamic> j) => AdminUser(
        id: j['id'] as int,
        username: j['username'] as String,
        displayName: (j['display_name'] as String?) ?? j['username'] as String,
        email: j['email'] as String?,
        role: (j['role'] as String?) ?? 'partner',
        active: j['is_active'] != false,
        lastLogin: DateTime.tryParse((j['last_login'] as String?) ?? ''),
        avatarColor: j['avatar_color'] as String?,
        avatarUrl: j['avatar_url'] as String?,
        devices: (j['devices'] as int?) ?? 0,
        links: ((j['links'] as Map?) ?? const {}).map((k, v) => MapEntry('$k', v as bool?)),
      );
}

class HaEntity {
  final String entityId;
  final String name;
  final String domain;
  final String? state;
  final String? unit;
  final bool controllable;

  const HaEntity({
    required this.entityId,
    required this.name,
    required this.domain,
    this.state,
    this.unit,
    this.controllable = false,
  });

  String get stateLabel => switch (state) {
        null => '',
        'on' => 'An',
        'off' => 'Aus',
        'unavailable' => 'Nicht verfügbar',
        _ => unit == null ? state! : '$state $unit',
      };

  factory HaEntity.fromJson(Map<String, dynamic> j) => HaEntity(
        entityId: j['entity_id'] as String,
        name: (j['name'] as String?) ?? j['entity_id'] as String,
        domain: (j['domain'] as String?) ?? (j['entity_id'] as String).split('.').first,
        state: j['state']?.toString(),
        unit: j['unit'] as String?,
        controllable: j['controllable'] == true,
      );
}

class HouseChoices {
  final String status;
  final List<HaEntity> items;
  final List<String> display;
  final List<String> control;
  final int max;

  const HouseChoices({
    required this.status,
    this.items = const [],
    this.display = const [],
    this.control = const [],
    this.max = 6,
  });

  factory HouseChoices.fromJson(Map<String, dynamic> j) {
    final sel = (j['selection'] as Map?)?.cast<String, dynamic>() ?? const {};
    List<String> ids(Object? v) => ((v as List?) ?? const []).map((e) => '$e').toList();
    return HouseChoices(
      status: (j['status'] as String?) ?? 'unavailable',
      items: ((j['items'] as List?) ?? const []).whereType<Map<String, dynamic>>().map(HaEntity.fromJson).toList(),
      display: ids(sel['display']),
      control: ids(sel['control']),
      max: (sel['max'] as int?) ?? 6,
    );
  }
}

class LogEntry {
  final DateTime? time;
  final String level;
  final String source;
  final String message;
  const LogEntry({this.time, required this.level, required this.source, required this.message});

  factory LogEntry.fromJson(Map<String, dynamic> j) => LogEntry(
        time: DateTime.tryParse((j['time'] as String?) ?? '')?.toLocal(),
        level: (j['level'] as String?) ?? 'WARNING',
        source: (j['source'] as String?) ?? '',
        message: (j['message'] as String?) ?? '',
      );
}

/// Öffentlicher Einrichtungsstatus (`/api/setup/status`).
class SetupStatus {
  final bool needsSetup;
  final String appName;
  final bool oidc;
  const SetupStatus({required this.needsSetup, this.appName = 'Familienhub', this.oidc = false});

  factory SetupStatus.fromJson(Map<String, dynamic> j) => SetupStatus(
        needsSetup: j['needs_setup'] == true,
        appName: (j['app_name'] as String?) ?? 'Familienhub',
        oidc: j['oidc'] == true,
      );
}

/// Ergebnis von „Verbindung testen“: ok, info (Hinweis) oder error.
class ConnectionResult {
  final bool ok;
  final String level;
  final String message;
  const ConnectionResult({required this.ok, required this.level, required this.message});

  factory ConnectionResult.fromJson(Map<String, dynamic> j) => ConnectionResult(
        ok: j['ok'] == true,
        level: (j['level'] as String?) ?? (j['ok'] == true ? 'ok' : 'error'),
        message: (j['message'] as String?) ?? '',
      );
}

/// Einladung: Person ist angelegt, Code zum Einlösen (nur direkt nach dem Erzeugen bekannt).
class InviteInfo {
  final int id;
  final String displayName;
  final String email;
  final String role;
  final DateTime? expiresAt;
  final bool expired;
  final String? code;
  final bool oidc;

  const InviteInfo({
    required this.id,
    required this.displayName,
    required this.email,
    required this.role,
    this.expiresAt,
    this.expired = false,
    this.code,
    this.oidc = false,
  });

  factory InviteInfo.fromJson(Map<String, dynamic> j) => InviteInfo(
        id: j['id'] as int,
        displayName: (j['display_name'] as String?) ?? '',
        email: (j['email'] as String?) ?? '',
        role: (j['role'] as String?) ?? 'partner',
        expiresAt: DateTime.tryParse((j['expires_at'] as String?) ?? '')?.toLocal(),
        expired: j['expired'] == true,
        code: j['code'] as String?,
        oidc: j['oidc'] == true,
      );
}
