package de.familienhub.app

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.SharedPreferences
import android.net.Uri
import android.os.Bundle
import android.widget.RemoteViews
import es.antonborri.home_widget.HomeWidgetLaunchIntent
import es.antonborri.home_widget.HomeWidgetPlugin
import es.antonborri.home_widget.HomeWidgetProvider

/** Widget „Einkauf“: offene Artikel im Stil des App-Themes; Tippen öffnet den Einkauf in der App. */
class ShoppingWidgetProvider : HomeWidgetProvider() {
    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray,
        widgetData: SharedPreferences,
    ) {
        val style = WidgetStyle.read(widgetData)
        val loggedIn = !widgetData.getString("widget_session", null).isNullOrEmpty()
        for (id in appWidgetIds) {
            val views = RemoteViews(context.packageName, R.layout.widget_shopping).apply {
                setTextViewText(R.id.shopping_count, if (loggedIn) widgetData.getString("shopping_count", "Einkauf") else "Einkauf")
                setTextViewText(R.id.shopping_items,
                    if (loggedIn) widgetData.getString("shopping_items", "App öffnen zum Laden") else "In der App anmelden")
                setTextViewText(R.id.shopping_updated, if (loggedIn) widgetData.getString("shopping_updated", "") else "")

                setTextColor(R.id.shopping_count, if (style.band != null) style.onBand else style.accent)
                setTextColor(R.id.shopping_items, style.text)
                setTextColor(R.id.shopping_updated, style.muted)
                WidgetStyle.apply(context, appWidgetManager, id, this, style, bandDp = 44f + style.borderDp)

                setOnClickPendingIntent(
                    R.id.widget_shopping_root,
                    HomeWidgetLaunchIntent.getActivity(context, MainActivity::class.java, Uri.parse("familienhub://open?route=/shopping")),
                )
            }
            appWidgetManager.updateAppWidget(id, views)
        }
    }

    override fun onAppWidgetOptionsChanged(context: Context, appWidgetManager: AppWidgetManager, appWidgetId: Int, newOptions: Bundle) {
        super.onAppWidgetOptionsChanged(context, appWidgetManager, appWidgetId, newOptions)
        onUpdate(context, appWidgetManager, intArrayOf(appWidgetId), HomeWidgetPlugin.getData(context))
    }
}
