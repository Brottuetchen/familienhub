import 'common.dart';
import 'plugin_card.dart';

/// Own stars: balance, what is reserved by open requests, the next reward and (parents) open decisions.
class StarsSummary {
  final bool enabled;
  final int balance;
  final int reserved;
  final int available;
  final StarReward? nextReward;
  final int pending; // parents: reward requests and confirmations waiting for a decision

  const StarsSummary({
    this.enabled = false,
    this.balance = 0,
    this.reserved = 0,
    this.available = 0,
    this.nextReward,
    this.pending = 0,
  });

  factory StarsSummary.fromJson(dynamic json) {
    if (json is! Map) return const StarsSummary();
    final next = json['next_reward'];
    final pending = json['pending'];
    return StarsSummary(
      enabled: json['enabled'] == true,
      balance: parseInt(json['balance']) ?? 0,
      reserved: parseInt(json['reserved']) ?? 0,
      available: parseInt(json['available']) ?? 0,
      nextReward: next is Map ? StarReward.fromJson(Map<String, dynamic>.from(next)) : null,
      pending: pending is Map ? parseInt(pending['total']) ?? 0 : 0,
    );
  }
}

class StarReward {
  final int id;
  final String title;
  final int price;
  final bool active;
  final int missing;

  /// Plugin action that runs when a parent approves this reward (only parents get to see it).
  final RewardActionRef? action;

  const StarReward(
      {required this.id, required this.title, required this.price, this.active = true, this.missing = 0, this.action});

  factory StarReward.fromJson(Map<String, dynamic> json) => StarReward(
        id: parseInt(json['id']) ?? 0,
        title: (json['title'] as String?) ?? '',
        price: parseInt(json['price']) ?? 0,
        active: json['active'] != false,
        missing: parseInt(json['missing']) ?? 0,
        action: RewardActionRef.fromJson(json['action']),
      );
}

class StarRequest {
  final int id;
  final int userId;
  final String userName;
  final String title;
  final int price;
  final String status; // pending | approved | declined | cancelled

  const StarRequest({
    required this.id,
    required this.userId,
    this.userName = '',
    required this.title,
    required this.price,
    required this.status,
  });

  factory StarRequest.fromJson(Map<String, dynamic> json) => StarRequest(
        id: parseInt(json['id']) ?? 0,
        userId: parseInt(json['user_id']) ?? 0,
        userName: (json['user_name'] as String?) ?? '',
        title: (json['title'] as String?) ?? '',
        price: parseInt(json['price']) ?? 0,
        status: (json['status'] as String?) ?? 'pending',
      );
}

class StarEntry {
  final int id;
  final int userId;
  final String userName;
  final int delta;
  final String kind; // task | reward | adjust
  final String status; // pending | confirmed | rejected
  final String title;

  const StarEntry({
    required this.id,
    required this.userId,
    this.userName = '',
    required this.delta,
    required this.kind,
    required this.status,
    required this.title,
  });

  factory StarEntry.fromJson(Map<String, dynamic> json) => StarEntry(
        id: parseInt(json['id']) ?? 0,
        userId: parseInt(json['user_id']) ?? 0,
        userName: (json['user_name'] as String?) ?? '',
        delta: parseInt(json['delta']) ?? 0,
        kind: (json['kind'] as String?) ?? 'task',
        status: (json['status'] as String?) ?? 'confirmed',
        title: (json['title'] as String?) ?? '',
      );
}

/// A child (or anyone with an account) as seen by parents.
class StarPerson {
  final int id;
  final String name;
  final int balance;
  final int available;

  const StarPerson({required this.id, required this.name, required this.balance, required this.available});

  factory StarPerson.fromJson(Map<String, dynamic> json) => StarPerson(
        id: parseInt(json['id']) ?? 0,
        name: (json['name'] as String?) ?? '',
        balance: parseInt(json['balance']) ?? 0,
        available: parseInt(json['available']) ?? 0,
      );
}

/// Everything the stars screen shows, loaded in one go (`/api/stars/...`).
class StarsOverview {
  final StarsSummary me;
  final List<StarReward> rewards;
  final List<StarRequest> requests; // own requests (children) or all open ones (parents)
  final List<StarEntry> history; // own history
  final List<StarEntry> awards; // parents: task completions waiting for confirmation
  final List<StarPerson> people; // parents
  final bool confirmTasks;

  const StarsOverview({
    required this.me,
    this.rewards = const [],
    this.requests = const [],
    this.history = const [],
    this.awards = const [],
    this.people = const [],
    this.confirmTasks = false,
  });
}
