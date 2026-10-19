/// Arrangement of the "Today" screen: ordered cards with visibility and size.
class TodayCard {
  final String id;
  final bool visible;
  final bool half; // two half cards sit side by side (bento themes only)
  const TodayCard(this.id, {this.visible = true, this.half = false});

  TodayCard copyWith({bool? visible, bool? half}) =>
      TodayCard(id, visible: visible ?? this.visible, half: half ?? this.half);

  Map<String, dynamic> toJson() => {'id': id, 'visible': visible, 'size': half ? 'half' : 'full'};
}

class TodayLayout {
  /// 'user' | 'family' | 'builtin'
  final String source;
  final List<TodayCard> cards;
  const TodayLayout(this.cards, {this.source = 'builtin'});

  /// Every card the screen knows, in the order of the built-in bento arrangement.
  static const knownIds = ['tasks', 'shopping', 'events', 'meals', 'reminders', 'house', 'birthdays', 'timetable'];

  /// Arrangement before the layout became customisable.
  static const builtin = TodayLayout([
    TodayCard('tasks'),
    TodayCard('shopping', half: true),
    TodayCard('events', half: true),
    TodayCard('meals'),
    TodayCard('reminders'),
    TodayCard('house'),
    TodayCard('birthdays'),
    TodayCard('timetable'),
  ]);

  /// Plain (non-bento) themes always stacked meals before shopping and events.
  static const _legacyList = ['tasks', 'meals', 'shopping', 'events', 'reminders', 'house', 'birthdays', 'timetable'];

  /// Unknown ids are dropped, cards the server did not mention are appended with their defaults.
  static TodayLayout normalize(Iterable<TodayCard> cards, {String source = 'builtin'}) {
    final seen = <String>{};
    final out = <TodayCard>[
      for (final c in cards)
        if (knownIds.contains(c.id) && seen.add(c.id)) c,
    ];
    out.addAll(builtin.cards.where((c) => !seen.contains(c.id)));
    return TodayLayout(out, source: source);
  }

  factory TodayLayout.fromJson(dynamic json) {
    final raw = json is Map ? json['cards'] : null;
    if (raw is! List) return builtin;
    final cards = <TodayCard>[
      for (final c in raw.whereType<Map>())
        if (c['id'] is String)
          TodayCard(c['id'] as String, visible: c['visible'] != false, half: c['size'] == 'half'),
    ];
    final source = json['source'];
    return normalize(cards, source: source is String ? source : 'user');
  }

  /// What the screen shows. Without any saved layout, plain themes keep their original single column.
  TodayLayout forStyle({required bool bento}) {
    if (bento || source != 'builtin') return this;
    return TodayLayout([for (final id in _legacyList) TodayCard(id)], source: source);
  }

  Map<String, dynamic> toJson() => {'cards': [for (final c in cards) c.toJson()]};
}
