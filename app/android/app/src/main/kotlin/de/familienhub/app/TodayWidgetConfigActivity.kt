package de.familienhub.app

import android.app.Activity
import android.appwidget.AppWidgetManager
import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import es.antonborri.home_widget.HomeWidgetPlugin

/**
 * Configure screen of the "Today" widget: tick the sections to show (at least one).
 * Opened when the widget is placed and, on Android 12+, via long-press -> reconfigure.
 */
class TodayWidgetConfigActivity : Activity() {
    private var widgetId = AppWidgetManager.INVALID_APPWIDGET_ID

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setResult(RESULT_CANCELED)
        widgetId = intent?.extras?.getInt(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID)
            ?: AppWidgetManager.INVALID_APPWIDGET_ID
        if (widgetId == AppWidgetManager.INVALID_APPWIDGET_ID) {
            finish()
            return
        }
        title = getString(R.string.config_title)

        val d = resources.displayMetrics.density
        fun dp(v: Int) = (v * d).toInt()
        val current = WidgetConfig.sections(this, widgetId).toSet()
        val boxes = Section.values().associateWith { section ->
            CheckBox(this).apply {
                text = getString(section.labelRes)
                textSize = 17f
                isChecked = section in current
                setPadding(dp(8), dp(10), dp(8), dp(10))
            }
        }

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(20), dp(24), dp(12))
            addView(TextView(context).apply { text = getString(R.string.config_hint); textSize = 15f })
            boxes.values.forEach { addView(it) }
            addView(LinearLayout(context).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.END
                setPadding(0, dp(12), 0, 0)
                addView(Button(context, null, android.R.attr.buttonBarButtonStyle).apply {
                    text = getString(R.string.config_cancel)
                    setOnClickListener { finish() }
                })
                addView(Button(context, null, android.R.attr.buttonBarButtonStyle).apply {
                    text = getString(R.string.config_save)
                    setOnClickListener {
                        val chosen = boxes.filter { it.value.isChecked }.keys
                        if (chosen.isEmpty()) {
                            Toast.makeText(context, R.string.config_min_one, Toast.LENGTH_SHORT).show()
                        } else {
                            save(chosen)
                        }
                    }
                })
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        setContentView(root)
    }

    private fun save(chosen: Collection<Section>) {
        WidgetConfig.save(this, widgetId, chosen)
        val manager = AppWidgetManager.getInstance(this)
        TodayWidgetProvider().onUpdate(this, manager, intArrayOf(widgetId), HomeWidgetPlugin.getData(this))
        setResult(RESULT_OK, Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId))
        finish()
    }
}
