extends SceneTree
const World = preload("res://scripts/world/world_state.gd")
const Agent = preload("res://scripts/cognition/agent.gd")

func _init() -> void:
    call_deferred("run")

func run() -> void:
    var w = World.new()
    var a = Agent.new(w, 405)
    a.set_neural_control(true)
    
    # Set hydration to low value to trigger DRINK action
    a.body.physiology.state.hydration = 0.24
    a.body.update_drives()
    
    # Set position and heading for sensing
    a.position = Vector3(-2.0, 0.0, 1.1)
    a.heading = Vector3.LEFT
    
    # Sample senses to populate memory
    a.senses.sample(w, a.position, a.heading, a.memory, a.body.needs, a.age)
    
    # Confirm utility_shadow_family() is non-empty
    var reference_family = a.utility_shadow_family()
    assert(not reference_family.is_empty(), "Utility reference family should not be empty")
    
    # Clear current and set phase to idle
    a.current.clear()
    a.phase = "idle"
    
    # Simulate neural bridge outage
    a.neural_bridge_unavailable("offline")
    
    # Call select_action() after outage
    a.select_action()
    
    # Assert that current remains empty and thought is set correctly
    assert(a.current.is_empty(), "Current should remain empty after neural outage")
    assert(a.thought == "Väntar på NeuralBrain.", "Thought should indicate waiting for NeuralBrain")
    
    # Accept a valid DRINK decision
    a.accept_neural_decision({"ok": true, "selected": "DRINK", "request_id": 100, "age": a.age})
    
    # Call select_action() again after accepting decision
    a.select_action()
    
    # Assert that neural control is resumed and action is correct
    assert(a.current.get("controller", "") == "neural", "Controller should be neural")
    assert(a.current.action == "drink", "Action should be drink")
    assert(a.current.target == "o2", "Target should be o2")
    
    print("PASS NeuralBrain outage regression test completed successfully.")
    quit(0)