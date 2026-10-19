import '../l10n/l10n.dart';
import 'common.dart';

/// A birthday or anniversary (`/api/birthdays`, and the Today card).
class Birthday {
  final int id;
  final String name;
  final String kind; // birthday | anniversary
  final int month;
  final int day;
  final int? year; // optional: without it no age is shown
  final int? userId; // linked hub user
  final int? remindDaysBefore; // null = no reminder
  final bool isYou; // the entry is the signed-in person's own: no gift ideas for them
  final int? giftCount; // open gift ideas; null when hidden from this person
  final DateTime? nextDate;
  final int daysUntil;
  final int? turns; // age / years at the next occurrence

  const Birthday({
    required this.id,
    required this.name,
    this.kind = 'birthday',
    this.month = 1,
    this.day = 1,
    this.year,
    this.userId,
    this.remindDaysBefore = 7,
    this.isYou = false,
    this.giftCount,
    this.nextDate,
    this.daysUntil = 0,
    this.turns,
  });

  bool get isAnniversary => kind == 'anniversary';

  /// "Grandma turns 80 in 3 days" / "Anna & Tom: 10 years tomorrow".
  String get whenText {
    final age = turns;
    if (isAnniversary) {
      return age == null ? l10n.birthdayWhenAnniversary(name, daysUntil) : l10n.birthdayWhenAnniversaryYears(name, age, daysUntil);
    }
    return age == null ? l10n.birthdayWhenBirthday(name, daysUntil) : l10n.birthdayWhenTurns(name, age, daysUntil);
  }

  factory Birthday.fromJson(Map<String, dynamic> json) => Birthday(
        id: parseInt(json['id']) ?? 0,
        name: (json['name'] as String?) ?? '',
        kind: (json['kind'] as String?) ?? 'birthday',
        month: parseInt(json['month']) ?? 1,
        day: parseInt(json['day']) ?? 1,
        year: parseInt(json['year']),
        userId: parseInt(json['user_id']),
        remindDaysBefore: json.containsKey('remind_days_before') ? parseInt(json['remind_days_before']) : 7,
        isYou: json['is_you'] == true,
        giftCount: parseInt(json['gift_count']),
        nextDate: parseDay(json['next_date']),
        daysUntil: parseInt(json['days_until']) ?? 0,
        turns: parseInt(json['turns']),
      );
}

/// A present idea collected for one entry.
class GiftIdea {
  final int id;
  final String text;
  final String? link;
  final bool done;
  final int? createdBy;

  const GiftIdea({required this.id, required this.text, this.link, this.done = false, this.createdBy});

  factory GiftIdea.fromJson(Map<String, dynamic> json) => GiftIdea(
        id: parseInt(json['id']) ?? 0,
        text: (json['text'] as String?) ?? '',
        link: json['link'] as String?,
        done: json['done'] == true,
        createdBy: parseInt(json['created_by']),
      );
}
