package de.familienhub.app

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.SharedPreferences
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.widget.RemoteViews
import es.antonborri.home_widget.HomeWidgetLaunchIntent
import es.antonborri.home_widget.HomeWidgetPlugin
import es.antonborri.home_widget.HomeWidgetProvider

/** Widget „Heute“: Texte und Stil schreibt die App (lib/services/home_widgets.dart). */
class TodayWidgetProvider : HomeWidgetProvider() {
    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray,
        widgetData: SharedPreferences,
    ) {
        val style = WidgetStyle.read(widgetData)
        // Ohne Widget-Sitzung (abgemeldet): keine Inhalte zeigen
        val loggedIn = !widgetData.getString("widget_session", null).isNullOrEmpty()
        for (id in appWidgetIds) {
            val views = RemoteViews(context.packageName, R.layout.widget_today).apply {
                setTextViewText(R.id.today_title, if (loggedIn) widgetData.getString("today_title", "Heute") else "Familienhub")
                setTextViewText(R.id.today_events,
                    if (loggedIn) widgetData.getString("today_events", "App öffnen zum Laden") else "In der App anmelden")
                val tasks = if (loggedIn) widgetData.getString("today_tasks", "") ?: "" else ""
                setTextViewText(R.id.today_tasks, tasks)
                setViewVisibility(R.id.today_tasks, if (tasks.isEmpty()) View.GONE else View.VISIBLE)
                val meal = if (loggedIn) widgetData.getString("today_meal", "") ?: "" else ""
                setTextViewText(R.id.today_meal, meal)
                setViewVisibility(R.id.today_meal, if (meal.isEmpty()) View.GONE else View.VISIBLE)
                setTextViewText(R.id.today_shopping, if (loggedIn) widgetData.getString("today_shopping", "") else "")
                setTextViewText(R.id.today_updated, if (loggedIn) widgetData.getString("today_updated", "") else "")

                setTextColor(R.id.today_title, if (style.band != null) style.onBand else style.accent)
                setTextColor(R.id.today_events, style.text)
                setTextColor(R.id.today_tasks, style.text)
                setTextColor(R.id.today_meal, style.text)
                setTextColor(R.id.today_shopping, style.green)
                setTextColor(R.id.today_updated, style.muted)
                WidgetStyle.apply(context, appWidgetManager, id, this, style, bandDp = 44f + style.borderDp)

                setOnClickPendingIntent(
                    R.id.widget_today_root,
                    HomeWidgetLaunchIntent.getActivity(context, MainActivity::class.java, Uri.parse("familienhub://open?route=/today")),
                )
                setOnClickPendingIntent(
                    R.id.today_shopping,
                    HomeWidgetLaunchIntent.getActivity(context, MainActivity::class.java, Uri.parse("familienhub://open?route=/shopping")),
                )
            }
            appWidgetManager.updateAppWidget(id, views)
        }
    }

    /** Größe geändert: Hintergrund passend neu zeichnen. */
    override fun onAppWidgetOptionsChanged(context: Context, appWidgetManager: AppWidgetManager, appWidgetId: Int, newOptions: Bundle) {
        super.onAppWidgetOptionsChanged(context, appWidgetManager, appWidgetId, newOptions)
        onUpdate(context, appWidgetManager, intArrayOf(appWidgetId), HomeWidgetPlugin.getData(context))
    }
}
