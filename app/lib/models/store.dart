/// Plugin and theme store (`GET /api/admin/store`, docs/store.md).
library;

List<String> _strings(Object? v) => ((v as List?) ?? const []).map((e) => '$e').toList();

/// Install state of an entry as the server computes it.
enum StoreState { available, installed, update, conflict }

StoreState _state(Object? raw) => switch (raw) {
      'installed' => StoreState.installed,
      'update' => StoreState.update,
      'conflict' => StoreState.conflict,
      _ => StoreState.available,
    };

/// One entry of a store index (texts already in the app language, with fallback by the server).
class StoreItem {
  final String source; // "official" or "custom-<id>"
  final bool verified;
  final String type; // "plugin" | "theme"
  final String id;
  final String name;
  final String summary;
  final String description;
  final String author;
  final String repo;
  final String version;
  final String sha;
  final String shortSha;
  final List<String> tags;
  final String minHubVersion;
  final bool compatible;
  final List<String> screenshots; // hub paths, loaded with the session
  final StoreState state;
  final String? installedVersion;

  const StoreItem({
    required this.source,
    required this.verified,
    required this.type,
    required this.id,
    required this.name,
    this.summary = '',
    this.description = '',
    this.author = '',
    this.repo = '',
    this.version = '',
    this.sha = '',
    this.shortSha = '',
    this.tags = const [],
    this.minHubVersion = '',
    this.compatible = true,
    this.screenshots = const [],
    this.state = StoreState.available,
    this.installedVersion,
  });

  bool get isPlugin => type == 'plugin';
  String get key => '$source/$type/$id';

  factory StoreItem.fromJson(Map<String, dynamic> j) => StoreItem(
        source: (j['source'] as String?) ?? 'official',
        verified: j['verified'] == true,
        type: (j['type'] as String?) ?? 'plugin',
        id: j['id'] as String,
        name: (j['name'] as String?) ?? j['id'] as String,
        summary: (j['summary'] as String?) ?? '',
        description: (j['description'] as String?) ?? '',
        author: (j['author'] as String?) ?? '',
        repo: (j['repo'] as String?) ?? '',
        version: (j['version'] as String?) ?? '',
        sha: (j['sha'] as String?) ?? '',
        shortSha: (j['short_sha'] as String?) ?? '',
        tags: _strings(j['tags']),
        minHubVersion: (j['min_hub_version'] as String?) ?? '',
        compatible: j['compatible'] != false,
        screenshots: _strings(j['screenshots']),
        state: _state(j['state']),
        installedVersion: j['installed_version'] as String?,
      );
}

/// A store source with its last fetch status (`ok`, `unreachable`, `invalid`).
class StoreSource {
  final String id;
  final String name;
  final String url;
  final bool verified;
  final bool removable;
  final String status;
  final bool stale;
  final int entries;
  final int skipped;

  const StoreSource({
    required this.id,
    required this.name,
    this.url = '',
    this.verified = false,
    this.removable = false,
    this.status = 'ok',
    this.stale = false,
    this.entries = 0,
    this.skipped = 0,
  });

  bool get ok => status == 'ok';

  /// Database id of a custom source (`custom-3` → 3).
  int? get dbId => id.startsWith('custom-') ? int.tryParse(id.substring(7)) : null;

  factory StoreSource.fromJson(Map<String, dynamic> j) => StoreSource(
        id: j['id'] as String,
        name: (j['name'] as String?) ?? j['id'] as String,
        url: (j['url'] as String?) ?? '',
        verified: j['verified'] == true,
        removable: j['removable'] == true,
        status: (j['status'] as String?) ?? 'ok',
        stale: j['stale'] == true,
        entries: (j['entries'] as num?)?.toInt() ?? 0,
        skipped: ((j['skipped'] as List?) ?? const []).length,
      );
}

class StoreListing {
  final bool installerEnabled;
  final List<StoreSource> sources;
  final List<StoreItem> items;

  const StoreListing({this.installerEnabled = true, this.sources = const [], this.items = const []});

  factory StoreListing.fromJson(Map<String, dynamic> j) => StoreListing(
        installerEnabled: j['installer_enabled'] != false,
        sources: ((j['sources'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(StoreSource.fromJson)
            .toList(),
        items: ((j['items'] as List?) ?? const []).whereType<Map<String, dynamic>>().map(StoreItem.fromJson).toList(),
      );
}

/// What the detail page shows before installing: plugin manifest at the pinned commit, or the theme colours.
class StoreDetails {
  final List<String> capabilities; // labels
  final List<String> hosts;
  final List<String> settings; // labels of the settings the plugin asks for
  final Map<String, String> colors; // theme only
  final List<String> warnings;

  const StoreDetails({
    this.capabilities = const [],
    this.hosts = const [],
    this.settings = const [],
    this.colors = const {},
    this.warnings = const [],
  });

  factory StoreDetails.fromJson(Map<String, dynamic> j) {
    final m = (j['manifest'] as Map?)?.cast<String, dynamic>() ?? const {};
    final theme = (j['theme'] as Map?)?.cast<String, dynamic>() ?? const {};
    return StoreDetails(
      capabilities: [
        for (final c in (m['capabilities'] as List?) ?? const [])
          if (c is Map) (c['label'] as String?) ?? '${c['id']}' else '$c'
      ],
      hosts: _strings(m['hosts']),
      settings: [
        for (final s in (j['settings'] as List?) ?? const [])
          if (s is Map) (s['label'] as String?) ?? '${s['key']}'
      ],
      colors: ((theme['colors'] as Map?) ?? const {}).map((k, v) => MapEntry('$k', '$v')),
      warnings: _strings(j['warnings']),
    );
  }
}
