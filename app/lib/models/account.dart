import 'common.dart';

class AppUser {
  final int id;
  final String username;
  final String? fullName;
  final bool isAdmin;

  /// Selbst gepflegter Anzeigename (Server liefert bereits mit Rückfall auf vollen Namen/Benutzernamen).
  final String? profileName;
  final String? avatarColor; // #RRGGBB
  final String? avatarUrl; // /api/users/{id}/avatar?v=…

  const AppUser({
    required this.id,
    required this.username,
    this.fullName,
    this.isAdmin = false,
    this.profileName,
    this.avatarColor,
    this.avatarUrl,
  });

  String get displayName {
    for (final n in [profileName, fullName]) {
      if (n != null && n.isNotEmpty) return n;
    }
    return username;
  }

  factory AppUser.fromJson(Map<String, dynamic> json) => AppUser(
        id: parseInt(json['id']) ?? 0,
        username: (json['username'] as String?) ?? '',
        fullName: json['full_name'] as String?,
        isAdmin: json['is_admin'] == true,
        profileName: json['display_name'] as String?,
        avatarColor: json['avatar_color'] as String?,
        avatarUrl: json['avatar_url'] as String?,
      );
}

/// Eintrag aus `/api/auth/people` für „Aufgabe für …“.
class Person {
  final int id;
  final String username;
  final String displayName;
  final String? avatarColor;
  final String? avatarUrl;

  const Person({required this.id, required this.username, required this.displayName, this.avatarColor, this.avatarUrl});

  factory Person.fromJson(Map<String, dynamic> json) => Person(
        id: parseInt(json['id']) ?? 0,
        username: (json['username'] as String?) ?? '',
        displayName: (json['display_name'] as String?) ?? (json['username'] as String? ?? ''),
        avatarColor: json['avatar_color'] as String?,
        avatarUrl: json['avatar_url'] as String?,
      );
}

class HealthInfo {
  final bool online;
  final bool oidc;
  final bool push;
  final String? version;

  const HealthInfo({required this.online, this.oidc = false, this.push = false, this.version});

  factory HealthInfo.fromJson(Map<String, dynamic> json) {
    final features = (json['features'] as Map?) ?? const {};
    return HealthInfo(
      online: json['status'] == 'online' || json['status'] == 'ok',
      oidc: features['oidc'] == true,
      push: features['push'] == true,
      version: json['version'] as String?,
    );
  }
}

class Reminder {
  final int id;
  final String title;
  final String? notes;
  final DateTime? dueAt;
  final bool completed;

  /// true: alle sehen sie und bekommen die Mitteilung; false: nur der Ersteller.
  final bool forFamily;
  final String recurrence;

  /// time: zu einem Zeitpunkt; arrival: wenn man nach Hause kommt (meldet Home Assistant).
  final String fireOn;

  bool get onArrival => fireOn == 'arrival';

  const Reminder({
    required this.id,
    required this.title,
    this.notes,
    this.dueAt,
    this.completed = false,
    this.forFamily = false,
    this.recurrence = 'none',
    this.fireOn = 'time',
  });

  factory Reminder.fromJson(Map<String, dynamic> json) => Reminder(
        id: parseInt(json['id']) ?? 0,
        title: (json['title'] as String?) ?? '',
        notes: json['notes'] as String?,
        dueAt: parseDate(json['due_at']),
        completed: json['completed'] == true,
        forFamily: json['for_family'] == true,
        recurrence: (json['recurrence'] as String?) ?? 'none',
        fireOn: (json['fire_on'] as String?) ?? 'time',
      );
}

/// Eintrag im Mitteilungsverlauf (`/api/me/notifications`).
class NotificationItem {
  final int id;
  final String title;
  final String body;
  final String category;
  final String? route;
  final String source;
  final DateTime? createdAt;
  final bool read;
  final bool pushed;

  const NotificationItem({
    required this.id,
    required this.title,
    this.body = '',
    this.category = 'system',
    this.route,
    this.source = 'hub',
    this.createdAt,
    this.read = false,
    this.pushed = true,
  });

  factory NotificationItem.fromJson(Map<String, dynamic> json) => NotificationItem(
        id: parseInt(json['id']) ?? 0,
        title: (json['title'] as String?) ?? '',
        body: (json['body'] as String?) ?? '',
        category: (json['category'] as String?) ?? 'system',
        route: json['route'] as String?,
        source: (json['source'] as String?) ?? 'hub',
        createdAt: parseDate(json['created_at']),
        read: json['read'] == true,
        pushed: json['pushed'] != false,
      );
}

class NotificationInbox {
  final int unread;
  final List<NotificationItem> items;
  const NotificationInbox({this.unread = 0, this.items = const []});

  factory NotificationInbox.fromJson(Map<String, dynamic> json) => NotificationInbox(
        unread: parseInt(json['unread']) ?? 0,
        items: ((json['items'] as List?) ?? const [])
            .whereType<Map<String, dynamic>>()
            .map(NotificationItem.fromJson)
            .toList(),
      );
}

/// Dienst-Schlüssel (Admin) für den Benachrichtigungs-Eingang. Klartext nur beim Anlegen.
class ServiceKeyInfo {
  final int id;
  final String name;
  final String hint;
  final DateTime? lastUsedAt;
  final String? key;

  const ServiceKeyInfo({required this.id, required this.name, required this.hint, this.lastUsedAt, this.key});

  factory ServiceKeyInfo.fromJson(Map<String, dynamic> json) => ServiceKeyInfo(
        id: parseInt(json['id']) ?? 0,
        name: (json['name'] as String?) ?? '',
        hint: (json['hint'] as String?) ?? '',
        lastUsedAt: parseDate(json['last_used_at']),
        key: json['key'] as String?,
      );
}

class Device {
  final int id;
  final String kind;
  final String? deviceName;
  final DateTime? lastSeen;

  const Device({required this.id, required this.kind, this.deviceName, this.lastSeen});

  factory Device.fromJson(Map<String, dynamic> json) => Device(
        id: parseInt(json['id']) ?? 0,
        kind: (json['kind'] as String?) ?? '',
        deviceName: json['device_name'] as String?,
        lastSeen: parseDate(json['last_seen']),
      );
}

/// Kategorien wie im Backend (`notify(category=…)`), mit deutschen Namen.
const notificationCategories = <String, String>{
  'task_assigned': 'Neue Aufgabe für mich',
  'task_due': 'Aufgabe fällig',
  'reminder': 'Erinnerungen',
  'shopping': 'Einkauf',
  'house': 'Haus (Waschmaschine, Müll …)',
  'media': 'Bücher & Medien',
  'documents': 'Dokumente',
  'system': 'System',
};

/// Wiederholungen wie im Backend (`recurrence`).
const reminderRecurrences = <String, String>{
  'none': 'Einmalig',
  'daily': 'Täglich',
  'weekdays': 'Werktags (Mo–Fr)',
  'weekly': 'Wöchentlich',
  'monthly': 'Monatlich',
};

class NotificationPref {
  final String category;
  final bool enabled;
  final String? quietStart; // HH:MM
  final String? quietEnd;

  const NotificationPref({
    required this.category,
    this.enabled = true,
    this.quietStart,
    this.quietEnd,
  });

  NotificationPref copyWith({bool? enabled, String? quietStart, String? quietEnd, bool clearQuiet = false}) =>
      NotificationPref(
        category: category,
        enabled: enabled ?? this.enabled,
        quietStart: clearQuiet ? null : (quietStart ?? this.quietStart),
        quietEnd: clearQuiet ? null : (quietEnd ?? this.quietEnd),
      );

  factory NotificationPref.fromJson(Map<String, dynamic> json) => NotificationPref(
        category: json['category'] as String,
        enabled: json['enabled'] != false,
        quietStart: json['quiet_start'] as String?,
        quietEnd: json['quiet_end'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'category': category,
        'enabled': enabled,
        'quiet_start': quietStart,
        'quiet_end': quietEnd,
      };
}

class CalDavAccountInfo {
  final String url;
  final String username;
  const CalDavAccountInfo({required this.url, required this.username});

  factory CalDavAccountInfo.fromJson(Map<String, dynamic> json) => CalDavAccountInfo(
        url: (json['url'] as String?) ?? '',
        username: (json['username'] as String?) ?? '',
      );
}

/// Persönlicher Zugangsschlüssel (z. B. für einen Sprachassistenten). Klartext gibt es nur beim Anlegen.
class ApiTokenInfo {
  final int id;
  final String name;
  final String hint;
  final DateTime? createdAt;
  final DateTime? lastUsedAt;
  final String? token;

  const ApiTokenInfo({
    required this.id,
    required this.name,
    required this.hint,
    this.createdAt,
    this.lastUsedAt,
    this.token,
  });

  factory ApiTokenInfo.fromJson(Map<String, dynamic> json) => ApiTokenInfo(
        id: parseInt(json['id']) ?? 0,
        name: (json['name'] as String?) ?? '',
        hint: (json['hint'] as String?) ?? '',
        createdAt: parseDate(json['created_at']),
        lastUsedAt: parseDate(json['last_used_at']),
        token: json['token'] as String?,
      );
}
