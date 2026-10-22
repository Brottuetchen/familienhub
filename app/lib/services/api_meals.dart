part of 'api_client.dart';

/// Meal plan, recipe book, recipe sources and Cookidoo.
mixin MealsApi on ApiClientBase {
  // ── Essen ──────────────────────────────────────────────────────────────────

  Future<ApiResult<MealWeek>> meals(String isoWeek) => _cachedGet(
      '/api/meals?week=$isoWeek', 'meals:$isoWeek', (j) => MealWeek.fromJson(j as Map<String, dynamic>));

  Future<void> addMeal(DateTime day, String title) => _send('POST', '/api/meals/plan',
      body: {'date': _dateOnly(day), 'custom_title': title, 'meal_type': 'dinner'});

  /// Nur Hub-Einträge; Cookidoo lehnt der Server mit 403 ab.
  Future<void> deleteMeal(int id) => _send('DELETE', '/api/meals/$id');

  // ── Recipe sources (Cookidoo, Mealie …) ────────────────────────────────────

  Future<List<RecipeSource>> recipeSources() async =>
      _maps(await _send('GET', '/api/recipe-sources')).map(RecipeSource.fromJson).toList();

  Future<SourceResult<CookidooRecipe>> searchRecipeSource(String source, String query) async => SourceResult.fromJson(
      await _send('GET', '/api/recipe-sources/$source/search?q=${Uri.encodeQueryComponent(query)}') as Map<String, dynamic>,
      CookidooRecipe.fromJson);

  /// Details for the recipe quick view; `source` is `hub`, `cookidoo` or `mealie`. The server answers softly
  /// (`status: unavailable`); only transport errors throw.
  Future<RecipeDetails> recipeDetails(String source, String id) async => RecipeDetails.fromJson(
      await _send('GET', '/api/recipe-sources/$source/recipes/${Uri.encodeComponent(id)}') as Map<String, dynamic>);

  Future<void> planFromSource(String source, DateTime day, String recipeId) =>
      _send('POST', '/api/recipe-sources/$source/plan', body: {'date': _dateOnly(day), 'recipe_id': recipeId});

  Future<void> unplanFromSource(String source, DateTime day, String recipeId) =>
      _send('DELETE', '/api/recipe-sources/$source/plan/${_dateOnly(day)}/${Uri.encodeComponent(recipeId)}');

  Future<int> sourceToShopping(String source, List<String> recipeIds) async => parseInt(
          ((await _send('POST', '/api/recipe-sources/$source/shopping', body: {'recipe_ids': recipeIds})) as Map<String, dynamic>)['added']) ??
      0;

  // ── Recipe book (hub) ──────────────────────────────────────────────────────

  Future<List<HubRecipe>> recipes({String? query}) async {
    final q = query == null || query.trim().isEmpty ? '' : '?q=${Uri.encodeQueryComponent(query.trim())}';
    return _maps(await _send('GET', '/api/recipes$q')).map(HubRecipe.fromJson).toList();
  }

  Future<HubRecipe> recipe(int id) async => HubRecipe.fromJson(await _send('GET', '/api/recipes/$id') as Map<String, dynamic>);

  Future<HubRecipe> saveRecipe(HubRecipe r) async => HubRecipe.fromJson(await (r.id == null
      ? _send('POST', '/api/recipes', body: r.toJson())
      : _send('PUT', '/api/recipes/${r.id}', body: r.toJson())) as Map<String, dynamic>);

  Future<void> deleteRecipe(int id) => _send('DELETE', '/api/recipes/$id');

  /// Reads the recipe on a web page (server side) into a draft; nothing is saved until [saveRecipe].
  Future<RecipeImportResult> importRecipePreview(String url) async => RecipeImportResult.fromJson(
      await _send('POST', '/api/recipes/import/preview', body: {'url': url}) as Map<String, dynamic>);

  Future<void> planRecipe(DateTime day, int recipeId) => _send('POST', '/api/meals/plan',
      body: {'date': _dateOnly(day), 'recipe_id': recipeId, 'meal_type': 'dinner'});

  /// Ingredients onto the family's current shopping list; returns how many were added.
  Future<int> recipeToShopping(int id) async =>
      parseInt((await _send('POST', '/api/recipes/$id/shopping') as Map<String, dynamic>)['added']) ?? 0;

  /// Ingredients of all recipes planned in the range (hub, Cookidoo, Mealie) onto the shopping list.
  /// Returns the summary: one line per source, or the server's message.
  Future<String> mealsToShoppingList({DateTime? start, DateTime? end}) async {
    final query = [if (start != null) 'start=${_dateOnly(start)}', if (end != null) 'end=${_dateOnly(end)}'];
    final json = await _send('POST', '/api/meals/shopping-list${query.isEmpty ? '' : '?${query.join('&')}'}')
        as Map<String, dynamic>;
    final lines = [
      for (final s in (json['sources'] as List? ?? const []))
        if (s is Map && (s['message'] as String?)?.isNotEmpty == true) s['message'] as String,
    ];
    if (lines.isNotEmpty) return lines.join('\n');
    return (json['message'] as String?) ?? l10n.ingredientsAdded(json['added'] ?? 0);
  }

  // ── Cookidoo (Plugin) ──────────────────────────────────────────────────────

  Future<SourceResult<CookidooRecipe>> searchCookidoo(String query) async {
    final q = Uri(queryParameters: {'q': query}).query;
    return SourceResult.fromJson(
        await _send('GET', '/api/cookidoo/search?$q') as Map<String, dynamic>, CookidooRecipe.fromJson);
  }

  Future<void> planCookidoo(DateTime day, String recipeId) =>
      _send('POST', '/api/cookidoo/plan', body: {'date': _dateOnly(day), 'recipe_id': recipeId});

  Future<void> unplanCookidoo(DateTime day, String recipeId) =>
      _send('DELETE', '/api/cookidoo/plan/${_dateOnly(day)}/${Uri.encodeComponent(recipeId)}');

  /// Zutaten auf die Cookidoo-Einkaufsliste; liefert die Anzahl.
  Future<int> cookidooToShopping(List<String> recipeIds) async {
    final json = await _send('POST', '/api/cookidoo/shopping', body: {'recipe_ids': recipeIds}) as Map<String, dynamic>;
    return parseInt(json['added']) ?? 0;
  }
}
