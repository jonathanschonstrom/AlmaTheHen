extends CanvasLayer
signal interaction(kind: String)
signal speed_changed(value: float)
signal pause_changed
signal save_requested
const Utility = preload("res://scripts/cognition/utility.gd")
const INK = Color("edf0de")
const MUTED = Color("9baea3")
const ACCENT = Color("dfba76")
var labels = {}
var bars = {}
var tabs: TabContainer
var memory_text: RichTextLabel
var model_text: RichTextLabel
var neural_text: RichTextLabel
var save_label: Label
var age_label: Label
var toast: Label
var pause_button: Button
var presence_button: Button
var panel: PanelContainer
var controls: Control
var toast_time = 0.0

func _ready() -> void:
	var root = Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	var theme = Theme.new()
	var font = SystemFont.new()
	font.font_names = PackedStringArray(["Segoe UI", "Noto Sans", "sans-serif"])
	theme.default_font = font
	theme.default_font_size = 16
	theme.set_color("font_color", "Label", INK)
	theme.set_color("default_color", "RichTextLabel", INK)
	theme.set_color("font_color", "Button", INK)
	theme.set_color("font_hover_color", "Button", ACCENT)
	theme.set_stylebox("normal", "Button", style(Color("30473f"), 8, 12, 8))
	theme.set_stylebox("hover", "Button", style(Color("3f5b4e"), 8, 12, 8))
	theme.set_stylebox("pressed", "Button", style(Color("577260"), 8, 12, 8))
	theme.set_stylebox("focus", "Button", style(Color(0, 0, 0, 0), 8, 0, 0))
	theme.set_stylebox("panel", "TabContainer", style(Color("1a2b25"), 0, 0, 8))
	theme.set_stylebox("tab_selected", "TabContainer", style(Color("30473f"), 5, 13, 9))
	theme.set_stylebox("tab_unselected", "TabContainer", style(Color("1a2b25"), 5, 13, 9))
	theme.set_color("font_selected_color", "TabContainer", ACCENT)
	theme.set_color("font_unselected_color", "TabContainer", MUTED)
	root.theme = theme
	var title = VBoxContainer.new()
	title.position = Vector2(34, 28)
	title.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(title)
	add_label(title, "B I R D A I    /    NEURALBRAIN CONTROL", 14, ACCENT)
	add_label(title, "Almas lilla gård", 34, INK)
	add_label(title, "80 % höna · 20 % papegoja · egna val", 16, MUTED)
	age_label = add_label(title, "", 14, MUTED)
	labels.food_stock = add_label(title, "", 13, ACCENT)
	var hint = add_label(root, "Höger mus: vrid · Hjul: zoom\nKlicka på golvet för att flytta din närvaro", 14, MUTED)
	hint.position = Vector2(34, 172)
	panel = PanelContainer.new()
	panel.set_anchors_and_offsets_preset(Control.PRESET_RIGHT_WIDE)
	panel.offset_left = -405
	panel.add_theme_stylebox_override("panel", style(Color("1a2b25"), 0, 23, 24))
	root.add_child(panel)
	var column = VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	panel.add_child(column)
	add_label(column, "INRE TILLSTÅND", 13, ACCENT)
	add_label(column, "En individ. Egna erfarenheter.", 20, INK)
	save_label = add_label(column, "", 12, MUTED)
	tabs = TabContainer.new()
	tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(tabs)
	var overview = tab_scroll("Överblick")
	heading(overview, "KÄNNER")
	labels.emotion = add_label(overview, "Nyfiken", 27, INK)
	heading(overview, "DRIVKRAFTER")
	add_label(overview, "Härleds ur kroppen · hög stapel = starkare driv", 12, MUTED)
	var names = {"hunger": "Hunger", "thirst": "Törst", "fatigue": "Vila", "safety": "Trygghet", "social": "Sällskap", "boredom": "Stimulans", "comfort": "Fjädervård"}
	for key in names:
		var line = HBoxContainer.new()
		line.add_theme_constant_override("separation", 12)
		overview.add_child(line)
		var name_label = add_label(line, names[key], 14, MUTED)
		name_label.custom_minimum_size.x = 82
		var bar = ProgressBar.new()
		bar.max_value = 100
		bar.show_percentage = false
		bar.custom_minimum_size = Vector2(160, 9)
		bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		bar.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		bar.add_theme_stylebox_override("background", style(Color("32463b"), 5, 0, 0))
		bar.add_theme_stylebox_override("fill", style(Color("9bbc94"), 5, 0, 0))
		line.add_child(bar)
		bars[key] = bar
		labels[key] = add_label(line, "0 %", 14, INK)
		labels[key].custom_minimum_size.x = 41
	for key in ["Plats", "Fokus", "Tänker", "Gör", "Mål", "Förväntar sig"]:
		heading(overview, key.to_upper())
		labels[key] = add_label(overview, "", 16, INK)
		labels[key].autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	heading(overview, "NEURAL CONTROL")
	labels.neural = add_label(overview, "Offline · NeuralBrain väntar", 14, MUTED)
	labels.neural.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	heading(overview, "RELEVANTA MINNEN")
	labels.memories = add_label(overview, "Inga erfarenheter ännu.", 14, MUTED)
	labels.memories.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	var memory_column = tab_scroll("Minne")
	add_label(memory_column, "Arbetsminne & erfarenheter", 21, INK)
	memory_text = rich(memory_column)
	var model_column = tab_scroll("Modell")
	add_label(model_column, "Varför detta val?", 21, INK)
	model_text = rich(model_column)
	var neural_column = tab_scroll("Neural")
	add_label(neural_column, "NeuralBrain v0.2.6 · BG100 · neural actuator control · utility reference only", 21, INK)
	neural_text = rich(neural_column)
	controls = PanelContainer.new()
	controls.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	controls.offset_left = 28
	controls.offset_top = -153
	controls.offset_right = 1007
	controls.offset_bottom = -24
	controls.add_theme_stylebox_override("panel", style(Color("21372f"), 12, 16, 12))
	root.add_child(controls)
	var rows = VBoxContainer.new()
	rows.add_theme_constant_override("separation", 9)
	controls.add_child(rows)
	var row1 = HBoxContainer.new()
	row1.add_theme_constant_override("separation", 8)
	rows.add_child(row1)
	button(row1, "Tryck gul knapp", func(): interaction.emit("experiment"))
	button(row1, "Mjukt lockläte", func(): interaction.emit("call"))
	button(row1, "Försiktig kontakt", func(): interaction.emit("touch"))
	presence_button = button(row1, "Lämna rummet", func(): interaction.emit("presence"))
	button(row1, "Plötsligt ljud", func(): interaction.emit("noise"))
	var row2 = HBoxContainer.new()
	row2.add_theme_constant_override("separation", 8)
	rows.add_child(row2)
	pause_button = button(row2, "Pausa", func(): pause_changed.emit())
	for speed in [1, 3, 8]:
		button(row2, "%d×" % speed, func(): speed_changed.emit(float(speed)))
	button(row2, "Fyll fröskål", func(): interaction.emit("refill"))
	button(row2, "Spara", func(): save_requested.emit())
	toast = add_label(row2, "Hon väljer själv vad hon gör.", 13, MUTED)
	toast.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	toast.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	toast.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

func tab_scroll(title: String) -> VBoxContainer:
	var scroll = ScrollContainer.new()
	scroll.name = title
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	tabs.add_child(scroll)
	var column = VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 6)
	scroll.add_child(column)
	return column

func rich(parent: Node) -> RichTextLabel:
	var label = RichTextLabel.new()
	label.bbcode_enabled = true
	label.fit_content = true
	label.scroll_active = false
	label.selection_enabled = true
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.add_theme_font_size_override("normal_font_size", 14)
	parent.add_child(label)
	return label

func heading(parent: Node, text: String) -> void:
	var label = add_label(parent, text, 12, ACCENT)
	label.custom_minimum_size.y = 24
	label.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM

func add_label(parent: Node, text: String, size: int, color: Color) -> Label:
	var label = Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	parent.add_child(label)
	return label

func button(parent: Node, text: String, callback: Callable) -> Button:
	var control = Button.new()
	control.text = text
	control.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	control.pressed.connect(callback)
	control.add_theme_font_size_override("font_size", 14)
	parent.add_child(control)
	return control

func style(color: Color, radius: int, margin_x: int, margin_y: int) -> StyleBoxFlat:
	var box = StyleBoxFlat.new()
	box.bg_color = color
	box.set_corner_radius_all(radius)
	box.content_margin_left = margin_x
	box.content_margin_right = margin_x
	box.content_margin_top = margin_y
	box.content_margin_bottom = margin_y
	return box

func announce(message: String) -> void:
	toast.text = message
	toast_time = 5.0

func update(agent, persistence, paused: bool, speed: float, dt: float) -> void:
	toast_time -= dt
	if toast_time <= 0:
		toast.text = "Hon väljer själv · %d× tid" % int(speed)
	age_label.text = "LIVSTID  %02d:%02d   ·   %d egna beslut" % [int(agent.age) / 60, int(agent.age) % 60, agent.decision_count]
	var remaining = int(ceil(agent.world.experiment_wait()))
	var food_state = "%d/%d portioner" % [int(agent.world.objects.o1.stock), int(agent.world.BOWL_CAPACITY)]
	var reward_state = "belöning kvar" if agent.world.objects.o9.stock > 0 else ("gul knapp redo" if remaining == 0 else "gul knapp om %d:%02d" % [remaining / 60, remaining % 60])
	labels.food_stock.text = "Fröskål: %s · experiment: %s" % [food_state, reward_state]
	save_label.text = persistence.message
	pause_button.text = "Fortsätt" if paused else "Pausa"
	presence_button.text = "Lämna rummet" if agent.world.objects.o8.active else "Kom tillbaka"
	labels.emotion.text = agent.body.emotion
	for key in bars:
		var value = float(agent.body.needs[key]) * 100
		bars[key].value = value
		labels[key].text = "%d %%" % int(value)
	var target = agent.current.get("target", agent.senses.focus)
	labels["Fokus"].text = agent.memory.objects.get(agent.senses.focus, {}).get("label", "Rummet omkring mig")
	labels["Plats"].text = agent.world.area_name(agent.position)
	if not agent.support_id.is_empty():
		labels["Plats"].text += " · sitter %.0f cm över marken" % (agent.position.y * 100)
	labels["Tänker"].text = agent.thought
	var action = agent.current.get("action", "look")
	var target_label = agent.memory.objects.get(target, {}).get("label", "")
	labels["Gör"].text = ("Går mot " + target_label.to_lower()) if agent.phase == "approach" and not target_label.is_empty() else Utility.ACTION_NAMES.get(action, "Observerar")
	if agent.phase == "ascend":
		labels["Gör"].text = "Flyger upp och försöker landa" if agent.ascent_powered else "Hoppar upp och försöker landa"
	elif agent.phase == "descend":
		labels["Gör"].text = "Tar sig ner från sittpinnen"
	labels["Mål"].text = agent.current.get("goal", "Orientera sig")
	var confidence = float(agent.current.get("confidence", 0))
	labels["Förväntar sig"].text = expectation(agent.current.get("expected", {}))
	var shadow = agent.neural_shadow
	var bridge_status = str(shadow.get("bridge_status", "offline"))
	if shadow.get("ok", false):
		var neural_pick = str(shadow.get("selected", "?"))
		var utility_pick = str(shadow.get("utility_family", agent.action_family(action)))
		var relation = "samma" if shadow.get("agreement", false) else "olika"
		if agent.neural_control_enabled:
			labels.neural.text = "%s · neural %s styr / utility %s referens · %s" % [bridge_status.capitalize(), neural_pick, utility_pick, relation]
		else:
			labels.neural.text = "%s · shadow neural %s / utility %s · %s" % [bridge_status.capitalize(), neural_pick, utility_pick, relation]
	else:
		var authority = "ingen utility-fallback" if agent.neural_control_enabled else "utility styr kroppen"
		labels.neural.text = "%s · %s%s" % [bridge_status.capitalize(), authority, (" · " + str(shadow.get("error", ""))) if shadow.has("error") else ""]
	if confidence > 0:
		labels["Förväntar sig"].text += " · %d %% erfarenhetsstöd" % int(confidence * 100)
	elif not agent.current.get("expected", {}).is_empty():
		labels["Förväntar sig"].text += " · instinkt / motoriskt försök"
	var relevant = agent.memory.relevant(target, 2)
	labels.memories.text = "Inga erfarenheter av detta ännu."
	if not relevant.is_empty():
		labels.memories.text = "\n\n".join(relevant.map(func(e): return e.outcome))
	if tabs.current_tab == 1:
		var text = "[color=#dfba76]JUST NU[/color]\n"
		for item in agent.memory.working:
			text += "%s · %s\n" % [item.kind.capitalize(), item.text]
		text += "\n[color=#dfba76]EPISODER · %d totalt, %d bevarade[/color]\n" % [agent.memory.total_episodes, agent.memory.episodes.size()]
		for event in agent.memory.relevant("", 25):
			text += "\n[b]%02d:%02d · %s[/b]\n%s\n[color=#9baea3]Återkoppling %+.2f[/color]\n" % [int(event.time) / 60, int(event.time) % 60, Utility.ACTION_NAMES.get(event.action, event.action), event.outcome, event.reward]
		memory_text.text = text
	if tabs.current_tab == 2:
		var text = "[color=#dfba76]UTILITY-REFERENS (STYR INTE)[/color]\n" if agent.neural_control_enabled else "[color=#dfba76]HANDLINGAR VID SENASTE VALET[/color]\n"
		for candidate in agent.utility.ranked.slice(0, 5):
			text += "%.2f   %s · %s\n" % [candidate.score, Utility.ACTION_NAMES.get(candidate.action, candidate.action), agent.memory.objects.get(candidate.target, {}).get("label", "kroppen")]
		text += "\nHärledda drivkrafter + förväntad nytta + ny information\n− avstånd − risk − upprepning.\n"
		var ps = agent.body.physiology.state
		text += "\n[color=#dfba76]KROPP · FYSIOLOGI[/color]\n"
		text += "Metabol energireserv %d %% · Magsäck %d %% · Tarmenergi %d %%\n" % [ps.metabolic_energy * 100, ps.stomach_fill * 100, ps.gut_energy * 100]
		text += "Vätskestatus %d %% · Sömntryck %d %% · Fysisk trötthet %d %%\n" % [ps.hydration * 100, ps.sleep_pressure * 100, ps.physical_fatigue * 100]
		text += "Akut rädsla %d %% · Stressbelastning %d %% · Fjäderstatus %d %%\n" % [ps.acute_fear * 100, ps.stress_load * 100, ps.feather_condition * 100]
		text += "Social mättnad %d %% · Stimulationsmättnad %d %%\n" % [ps.social_satiation * 100, ps.stimulation_satiation * 100]
		text += "Homeostatisk avvikelse %.3f\n" % agent.body.homeostatic_error()
		text += "\n[color=#dfba76]RELATION TILL DIG[/color]\nBekantskap %d %% · Tillit %d %%\nAnknytning %d %%\nPositiva möten %d · skrämmande %d\n" % [agent.relationship.familiarity * 100, agent.relationship.trust * 100, agent.relationship.attachment * 100, agent.relationship.positive, agent.relationship.negative]
		text += "\n[color=#dfba76]VINGAR · LÄR GENOM ATT PROVA[/color]\nBörjade markbunden. %d egna försök.\nBästa uppmätta lyft: %.0f cm\nSenast: %.0f cm / %.2f s i luften\nVingtiming: %.3f\n" % [agent.learning.flight.trials, agent.learning.flight.best_height * 100, agent.learning.flight.last_height * 100, agent.learning.flight.airtime, agent.learning.flight.timing]
		text += "\n[color=#dfba76]PERSONLIGHET · 80/20[/color]\n"
		var names = {"boldness": "Mod", "curiosity": "Nyfikenhet", "sociality": "Socialitet", "persistence": "Envishet", "playfulness": "Lekfullhet"}
		for key in names:
			text += "%s   %d %%\n" % [names[key], agent.personality[key] * 100]
		text += "\n[color=#dfba76]INLÄRDA SAMBAND · %d[/color]\n" % agent.learning.models.size()
		for context in ["lamp_lit", "lamp_dark"]:
			var button_model = agent.learning.model("o5", "peck", context)
			if button_model.count > 0:
				text += "\nExperimentknapp · %s · %d försök\n%s\n" % ["lampan lyste" if context == "lamp_lit" else "lampan var mörk", button_model.count, button_model.outcome]
		for id in agent.memory.objects:
			var record = agent.memory.objects[id]
			for verb in record.facts:
				text += "\n%s · %s\n%s\n" % [record.label, Utility.ACTION_NAMES.get(verb, verb), record.facts[verb].outcome]
		text += "\nSenaste belöning %+.3f\nPrediktionsfel %+.3f\nIndivid %s\n" % [agent.last_reward, agent.last_prediction_error, agent.individual_id]
		model_text.text = text

	if tabs.current_tab == 3:
		var text = "[color=#dfba76]STATUS[/color]\n"
		text += "Bridge: %s\n" % str(shadow.get("bridge_status", "offline"))
		if not shadow.get("ok", false):
			text += "Nengo/NeuralBrain är inte aktiv.\n"
			if shadow.has("error"):
				text += "[color=#9baea3]%s[/color]\n" % str(shadow.error)
			if agent.neural_control_enabled:
				text += "\nIngen utility-fallback används; Alma väntar på NeuralBrain.\n"
			else:
				text += "\nShadow mode: utility-systemet styr Alma.\n"
		else:
			text += "Backend: %s · cirka %d neuroner\n" % [str(shadow.get("backend", "nengo")), int(shadow.get("neurons", 0))]
			text += "Neuralt val: [b]%s[/b]\n" % str(shadow.get("selected", "?"))
			text += "Utility-familj: %s\n" % str(shadow.get("utility_family", "?"))
			text += "Överens: %s · neural marginal %d %% · historik %d %% (%d prov)\n" % ["ja" if shadow.get("agreement", false) else "nej", int(float(shadow.get("confidence", 0.0)) * 100.0), int(float(shadow.get("agreement_rate", 0.0)) * 100.0), int(shadow.get("samples", 0))]
			var commitment = shadow.get("commitment", {})
			if not str(commitment.get("prior_action", "")).is_empty() and float(commitment.get("bias", 0.0)) > 0.001:
				text += "Kort motoriskt åtagande: %s · bias +%.3f · %.0f %% kvar\n" % [str(commitment.get("prior_action", "")), float(commitment.get("bias", 0.0)), float(commitment.get("remaining", 0.0)) * 100.0]
			text += "\n[color=#dfba76]NEURAL HANDLINGSKONKURRENS[/color]\n"
			var action_values = shadow.get("action_values", {})
			var competition_values = shadow.get("competition_values", action_values)
			var affordance_gates = shadow.get("affordance_gates", {})
			var ordered = []
			for family in competition_values:
				ordered.append({"family": family, "value": float(competition_values[family])})
			ordered.sort_custom(func(a, b): return a.value > b.value)
			for item in ordered:
				var raw_value = float(action_values.get(item.family, item.value))
				var gate = float(affordance_gates.get(item.family, 1.0))
				text += "%.3f <- %.3f   %s · affordance %.2f\n" % [item.value, raw_value, item.family, gate]
			text += "\n[color=#dfba76]IN TILL HJÄRNAN[/color]\n"
			var inputs = agent.neural_inputs()
			text += "Kropp  hunger %.2f · törst %.2f · vila %.2f · utforska %.2f · social %.2f · säkerhet %.2f · fjädervård %.2f\n" % [inputs.hunger, inputs.thirst, inputs.rest, inputs.explore, inputs.social, inputs.safety, inputs.comfort]
			text += "Miljö  mat %.2f · vatten %.2f · människa %.2f · viloplats %.2f · vårdplats %.2f\n" % [inputs.food, inputs.water, inputs.person, inputs.rest_site, inputs.care_site]
			text += "Novelty %.2f · manipulerbart %.2f · rörelse %.2f · öppen yta %.2f\n" % [inputs.novelty, inputs.manipulable, inputs.motion, inputs.open_space]
			if agent.neural_control_enabled:
				text += "\n[color=#9baea3]CONTROL: NeuralBrain väljer handlingsfamilj och styr kroppen. Utility loggas endast som referens.[/color]"
			else:
				text += "\n[color=#9baea3]SHADOW: det neurala valet påverkar inte kroppen.[/color]"
		neural_text.text = text

func expectation(effects: Dictionary) -> String:
	if effects.is_empty():
		return "Okänt. Försöket ger ny information."
	var parts = []
	var names = {"hunger": "Mindre hunger", "thirst": "Mindre törst", "fatigue": "Mer energi", "safety": "Mer trygghet", "boredom": "Ny stimulans", "social": "Närhet", "comfort": "Vårdade fjädrar", "food_access": "Mat blir tillgänglig"}
	for key in effects:
		if float(effects[key]) > 0.02:
			parts.append(names.get(key, key))
	return ", ".join(parts) if not parts.is_empty() else "Liten eller osäker förändring."
