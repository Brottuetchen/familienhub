part of 'api_client.dart';

/// Kids mode (stars and rewards) and birthdays.
mixin FamilyApi on ApiClientBase {
  // ── Sterne und Belohnungen (Kindermodus) ───────────────────────────────────

  Future<ApiResult<StarsSummary>> starsMe() => _cachedGet('/api/stars/me', 'stars:me', StarsSummary.fromJson);

  /// Everything the stars screen shows. Parents also get the open decisions and the children's balances.
  Future<StarsOverview> starsOverview({required bool parent}) async {
    final me = StarsSummary.fromJson(await _send('GET', '/api/stars/me'));
    final rewards = _maps((await _send('GET', '/api/stars/rewards'))['items']).map(StarReward.fromJson).toList();
    final settings = await _send('GET', '/api/stars/settings');
    final confirm = settings is Map && settings['confirm_tasks'] == true;
    if (!parent) {
      final requests = _maps((await _send('GET', '/api/stars/requests'))['items']).map(StarRequest.fromJson).toList();
      final ledger = _maps((await _send('GET', '/api/stars/ledger'))['items']).map(StarEntry.fromJson).toList();
      return StarsOverview(me: me, rewards: rewards, requests: requests, history: ledger, confirmTasks: confirm);
    }
    final pending = await _send('GET', '/api/stars/pending') as Map<String, dynamic>;
    final people = _maps((await _send('GET', '/api/stars/people'))['items']).map(StarPerson.fromJson).toList();
    return StarsOverview(
      me: me,
      rewards: rewards,
      requests: _maps(pending['requests']).map(StarRequest.fromJson).toList(),
      awards: _maps(pending['awards']).map(StarEntry.fromJson).toList(),
      people: people,
      confirmTasks: confirm,
    );
  }

  Future<List<StarEntry>> starsHistory(int userId) async =>
      _maps((await _send('GET', '/api/stars/ledger?user_id=$userId'))['items']).map(StarEntry.fromJson).toList();

  Future<void> requestReward(int rewardId) =>
      _send('POST', '/api/stars/requests', replayOn401: false, body: {'reward_id': rewardId});

  Future<void> cancelRewardRequest(int id) => _send('POST', '/api/stars/requests/$id/cancel', replayOn401: false);

  /// Approving can run a plugin action of the reward: its outcome comes back (null if the reward has none).
  Future<RewardActionResult?> decideRewardRequest(int id, {required bool approve}) async {
    final res = await _send('POST', '/api/stars/requests/$id/${approve ? 'approve' : 'decline'}', replayOn401: false);
    return res is Map ? RewardActionResult.fromJson(res['action_result']) : null;
  }

  /// Actions of active plugins a parent can attach to a reward.
  Future<List<RewardActionChoice>> rewardActionChoices() async =>
      RewardActionChoice.listFromJson(await _send('GET', '/api/stars/reward-actions'));

  Future<void> decideStarEntry(int id, {required bool confirm}) =>
      _send('POST', '/api/stars/ledger/$id/${confirm ? 'confirm' : 'reject'}', replayOn401: false);

  /// [setAction]: also send [action] when editing (null removes the action; left out it stays as it is).
  Future<void> saveReward(
          {int? id, required String title, required int price, bool? active, RewardActionRef? action, bool setAction = false}) =>
      id == null
          ? _send('POST', '/api/stars/rewards',
              replayOn401: false, body: {'title': title, 'price': price, if (action != null) 'action': action.toJson()})
          : _send('PATCH', '/api/stars/rewards/$id', replayOn401: false, body: {
              'title': title,
              'price': price,
              if (active != null) 'active': active,
              if (setAction) 'action': action?.toJson(),
            });

  Future<void> setRewardActive(int id, bool active) =>
      _send('PATCH', '/api/stars/rewards/$id', replayOn401: false, body: {'active': active});

  Future<void> adjustStars(int userId, int delta, String title) => _send('POST', '/api/stars/adjust',
      replayOn401: false, body: {'user_id': userId, 'delta': delta, 'title': title});

  Future<void> setConfirmTasks(bool value) =>
      _send('PUT', '/api/stars/settings', replayOn401: false, body: {'confirm_tasks': value});

  // ── Geburtstage und Jahrestage ─────────────────────────────────────────────

  Future<List<Birthday>> birthdays() async =>
      _maps(await _send('GET', '/api/birthdays')).map(Birthday.fromJson).toList();

  Map<String, dynamic> _birthdayBody(String name, String kind, int month, int day, int? year, int? userId,
          int? remindDaysBefore) =>
      {
        'name': name,
        'kind': kind,
        'month': month,
        'day': day,
        'year': year,
        'user_id': userId,
        'remind_days_before': remindDaysBefore,
      };

  Future<void> saveBirthday({
    int? id,
    required String name,
    required String kind,
    required int month,
    required int day,
    int? year,
    int? userId,
    int? remindDaysBefore,
  }) =>
      _send(id == null ? 'POST' : 'PUT', id == null ? '/api/birthdays' : '/api/birthdays/$id',
          body: _birthdayBody(name, kind, month, day, year, userId, remindDaysBefore));

  Future<void> deleteBirthday(int id) => _send('DELETE', '/api/birthdays/$id');

  Future<List<GiftIdea>> giftIdeas(int birthdayId) async =>
      _maps(await _send('GET', '/api/birthdays/$birthdayId/gifts')).map(GiftIdea.fromJson).toList();

  Future<void> addGiftIdea(int birthdayId, String text, {String? link}) => _send('POST', '/api/birthdays/$birthdayId/gifts',
      body: {'text': text, if (link != null && link.isNotEmpty) 'link': link});

  Future<void> setGiftIdeaDone(int birthdayId, int giftId, bool done) =>
      _send('PATCH', '/api/birthdays/$birthdayId/gifts/$giftId', body: {'done': done});

  Future<void> deleteGiftIdea(int birthdayId, int giftId) => _send('DELETE', '/api/birthdays/$birthdayId/gifts/$giftId');
}
