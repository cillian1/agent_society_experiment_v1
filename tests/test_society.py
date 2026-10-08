"""Quick checks that run offline (mock brains). Run with:  python -m unittest"""
import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from society import Society, default_agents, persistence, views
from society.config import OPUS, SONNET
from society.mind import parse_action
from society.mock import MockLLM
from society.llm import RouterLLM


def make(days=0, seed=3):
    sim = Society(default_agents(), RouterLLM(mock=MockLLM()), seed=seed)
    with redirect_stdout(io.StringIO()):
        sim.run(days)
    return sim


class ParsingTests(unittest.TestCase):
    def test_garbage_becomes_wait(self):
        self.assertEqual(parse_action("I refuse to answer in JSON", [])["action"], "wait")

    def test_unknown_target_becomes_all(self):
        act = parse_action('{"action": "say", "to": "Nobody", "message": "hi"}', ["Ada"])
        self.assertEqual((act["action"], act["to"]), ("say", "all"))

    def test_json_inside_chatter(self):
        act = parse_action('Sure! {"thought": "go", "action": "move", "direction": "east", "steps": 3} ok', [])
        self.assertEqual((act["action"], act["direction"], act["steps"]), ("move", "east", 3))


class SimulationTests(unittest.TestCase):
    def test_long_run_does_things(self):
        sim = make(250)
        actions = {h["action"] for a in list(sim.agents.values()) + [d["agent"] for d in sim.dead.values()] for h in a.history}
        self.assertTrue({"move", "gather", "eat", "say", "build", "craft"} <= actions, actions)
        self.assertGreater(sim.world.explored_pct(), 10)
        self.assertEqual(len(sim.stats), 251)

    def test_views_are_json(self):
        sim = make(30)
        json.dumps(views.state(sim))
        json.dumps(views.agent_detail(sim, next(iter(sim.agents))))

    def test_only_one_opus(self):
        sim = make()
        sim.set_model("Ada", "opus")
        sim.set_model("Brix", "opus")
        self.assertEqual(sim.agents["Ada"].model, SONNET)
        self.assertEqual(sim.agents["Brix"].model, OPUS)
        self.assertIsNone(sim.set_model("Ada", "bad model!"))

    def test_gift_and_chat_reply(self):
        sim = make()
        self.assertEqual(sim.gift("Ada", "food"), "3 food")
        self.assertEqual(sim.human_say(["Ada"], "hello"), ["Ada"])
        for _ in range(50):
            if not sim.chat[-1].get("pending"):
                break
            time.sleep(0.02)
        self.assertTrue(sim.chat[-1]["text"])
        self.assertEqual(sim.agents["Ada"].orders[-1][1], "hello")


class FamilyTests(unittest.TestCase):
    def test_pregnancy_baby_child_adult(self):
        from society.actions import apply
        from society.mind import parse_action
        sim = make()
        ada, brix = sim.agents["Ada"], sim.agents["Brix"]
        brix.x, brix.y = ada.x + 1, ada.y
        sim.world.tiles[brix.y][brix.x] = "grass"
        for p, o in ((ada, brix), (brix, ada)):
            p.bonds[o.name], p.food = 80, 5
        act = lambda who, to: apply(sim, who, parse_action(f'{{"action": "procreate", "to": "{to}", "baby_name": "Kiki"}}', [to]), sim.tick)
        self.assertIn("waiting", act(ada, "Brix"))
        self.assertIn("pregnant", act(brix, "Ada"))
        self.assertEqual(ada.pregnancy["father"], "Brix")
        for _ in range(10):
            sim.begin_day()
        kiki = sim.agents["Kiki"]
        self.assertIsNone(ada.pregnancy)
        self.assertEqual((kiki.parents, kiki.stage(sim.tick)), (["Ada", "Brix"], "baby"))
        self.assertIsNone(sim.prepare(kiki))                       # babies don't think
        self.assertLessEqual(kiki.dist(ada), 1)                      # carried by mum
        ada.food = 3
        self.assertIn("fed Kiki", apply(sim, ada, parse_action('{"action": "care", "to": "Kiki"}', ["Kiki"]), sim.tick))
        for _ in range(5):
            sim.begin_day()
        self.assertEqual(kiki.stage(sim.tick), "child")
        self.assertIsNotNone(sim.prepare(kiki))
        for _ in range(5):
            sim.begin_day()
        self.assertEqual(kiki.stage(sim.tick), "adult")

    def test_same_sex_cannot_conceive(self):
        from society.actions import apply
        from society.mind import parse_action
        sim = make()
        ada, cleo = sim.agents["Ada"], sim.agents["Cleo"]
        self.assertIn("woman and a man", apply(sim, ada, parse_action('{"action": "procreate", "to": "Cleo"}', ["Cleo"]), 0))


class AbilityTests(unittest.TestCase):
    def test_settlers_get_varied_abilities_and_food(self):
        sim = make()
        abilities = {tuple(vars(a.abilities).values()) for a in sim.agents.values()}
        self.assertGreater(len(abilities), 1)
        self.assertTrue(all(a.food >= 3 for a in sim.agents.values()))

    def test_instinct_eats_when_starving(self):
        sim = make()
        ada = sim.agents["Ada"]
        ada.hunger, ada.food = 90, 2
        sim.begin_day()
        self.assertLess(ada.hunger, 75)
        self.assertEqual(ada.food, 1)

    def test_tending_has_a_cooldown_and_plants_grow_alone(self):
        sim = make()
        w = sim.world
        x, y = next((x, y) for y in range(w.height) for x in range(w.width) if w.tiles[y][x] == "grass")
        w.plant(x, y)
        self.assertTrue(w.tend(x, y, "Ada", 1)[2])
        self.assertFalse(w.tend(x, y, "Brix", 2)[2])        # too soon - it just needs time
        for t in range(40):
            w.update(t)
        self.assertEqual(w.tiles[y][x], "crop")


class MovementTests(unittest.TestCase):
    def test_go_finds_a_way_around_water(self):
        from society.actions import apply
        sim = make()
        ada = sim.agents["Ada"]
        before = (ada.x, ada.y)
        out = apply(sim, ada, parse_action('{"action": "go", "to": "food"}', []), 1)
        self.assertTrue(out.startswith("walked") or out.startswith("you are already"), out)
        if out.startswith("walked"):
            self.assertNotEqual((ada.x, ada.y), before)
            for x, y in [(ada.x, ada.y)]:
                self.assertTrue(sim.world.walkable(x, y))

    def test_agents_can_pass_each_other(self):
        from society.actions import apply
        sim = make()
        ada, brix = sim.agents["Ada"], sim.agents["Brix"]
        w = sim.world
        y, x = next((y, x) for y in range(w.height) for x in range(w.width - 2)
                    if all(w.tiles[y][x + i] == "grass" for i in range(3)))
        ada.x, ada.y, brix.x, brix.y = x, y, x + 1, y
        self.assertIn("moved east 2", apply(sim, ada, parse_action('{"action": "move", "direction": "east", "steps": 2}', []), 1))


class PlanningTests(unittest.TestCase):
    def test_queued_steps_run_and_hunger_interrupts(self):
        sim = make()
        ada = sim.agents["Ada"]
        act = parse_action('{"action": "wait", "next": [{"action": "gather"}, {"action": "say", "to": "all", "message": "hi"}]}', [])
        sim.apply_decision(ada, act, {"heard": []})
        self.assertEqual(len(ada.queue), 2)
        self.assertEqual(sim.take_queued(ada)["action"], "gather")
        ada.hunger = 80
        self.assertIsNone(sim.take_queued(ada))                 # hungry -> stop and think again
        self.assertEqual(ada.queue, [])

    def test_reflection_sets_an_ambition(self):
        sim = make(8)
        self.assertTrue(any(a.ambition for a in sim.agents.values()))


class GameMasterTests(unittest.TestCase):
    def test_outcome_is_clamped_and_discoveries_work(self):
        from society.gm import apply_outcome
        sim = make()
        ada = sim.agents["Ada"]
        food = ada.food
        verdict = {"success": True, "story": "Ada smokes fish over a fire.", "gain": {"food": 99, "wood": -5},
                   "cost": {"stone": 50}, "hunger": -500, "health": 500,
                   "discovery": {"name": "Smoked Fish", "description": "food keeps longer", "effect": "harvest", "amount": 9}}
        out = apply_outcome(sim, ada, {"action": "attempt", "what": "smoke fish"}, verdict, 1)
        self.assertIn("DISCOVERY", out)
        self.assertEqual(ada.food, food + 3)                   # gains capped at 3
        self.assertEqual(sim.discoveries[0]["amount"], 1)      # effect capped
        self.assertEqual(sim.tech("harvest"), 1)
        self.assertIn("Smoked Fish", ada.log[-1] + " ".join(o.log[-1] for o in sim.agents.values()))
        # a second discovery straight away is refused (cooldown), as is a duplicate name
        apply_outcome(sim, ada, {"action": "attempt", "what": "x"}, {"success": True, "discovery":
                      {"name": "Wheel", "effect": "speed", "amount": 1}}, 2)
        self.assertEqual(len(sim.discoveries), 1)

    def test_unknown_effects_are_ignored(self):
        from society.gm import apply_outcome
        sim = make()
        apply_outcome(sim, sim.agents["Ada"], {"action": "attempt", "what": "fly"},
                      {"success": True, "discovery": {"name": "Flight", "effect": "teleport", "amount": 5}}, 1)
        self.assertEqual(sim.discoveries, [])


class TalkTests(unittest.TestCase):
    def test_talking_can_change_plans_and_queue_work(self):
        sim = make()
        sim.human_say(["Ada"], "please fetch wood, and make it your ambition to build us a hall")
        for _ in range(100):
            if not sim.chat[-1].get("pending"):
                break
            time.sleep(0.02)
        ada = sim.agents["Ada"]
        self.assertEqual(ada.plan, "fetch wood for the Human")
        self.assertEqual([q["action"] for q in ada.queue], ["go", "gather"])
        self.assertIn("ambition", ada.ambition)
        self.assertTrue(any("starting tomorrow" in c for c in sim.chat[-1]["changes"]))


class BuildingTests(unittest.TestCase):
    def test_buildings_have_functions_and_no_duplicates(self):
        from society.actions import apply
        sim = make()
        a, w = sim.agents["Ada"], sim.world
        x, y = next((x, y) for y in range(2, w.height - 2) for x in range(2, w.width - 2)
                    if all(w.tiles[y + dy][x + dx] == "grass" for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                    and not any(max(abs(o.x - x), abs(o.y - y)) <= 2 for o in sim.agents.values()))
        a.x, a.y, a.wood, a.stone, a.food, a.hunger = x, y, 1, 0, 6, 10
        do = lambda j: apply(sim, a, parse_action(j, []), 1)
        self.assertIn("still missing 3 wood, 1 stone", do('{"action": "build", "direction": "east", "title": "Granary"}'))
        self.assertIn("granary", sim.blueprints)              # the plan is now shared knowledge
        a.wood, a.stone = 10, 5
        self.assertIn("built", do('{"action": "build", "direction": "east", "title": "Granary"}'))
        self.assertIn("already", do('{"action": "build", "direction": "west", "title": "storehouse"}'))
        self.assertIn("stored 3 food", do('{"action": "store", "title": "food", "amount": 3}'))
        self.assertIn("took 2 food", do('{"action": "take", "title": "food", "amount": 2}'))
        do('{"action": "build", "direction": "north", "title": "hearth"}')
        a.hunger = 60
        self.assertIn("cooked", do('{"action": "eat"}'))
        self.assertLessEqual(a.hunger, 5)


class SolTests(unittest.TestCase):
    def test_sol_reviews_every_20_days_and_advises(self):
        sim = make(41)
        self.assertEqual([l["tick"] for l in sim.sol_log], [20, 40])
        advised = [a for a in sim.agents.values() if a.advice]
        self.assertTrue(advised)
        self.assertTrue(any(c.get("review") for c in sim.chat))

    def test_talking_to_sol(self):
        sim = make()
        self.assertEqual(sim.human_say(["Sol"], "Sol, get them building a well"), ["Sol"])
        for _ in range(100):
            if not sim.chat[-1].get("pending"):
                break
            time.sleep(0.02)
        self.assertEqual(sim.chat[-1]["from"], "Sol")
        self.assertTrue(sim.chat[-1]["changes"])


class SaveTests(unittest.TestCase):
    def test_round_trip_and_continue(self):
        sim = make(60)
        with tempfile.TemporaryDirectory() as d:
            persistence.SAVE_DIR = Path(d)
            persistence.save(sim, "t")
            again = persistence.load("t", sim.llm)
            self.assertEqual(json.dumps(again.to_dict(), sort_keys=True), json.dumps(sim.to_dict(), sort_keys=True))
            self.assertEqual(persistence.list_saves()[0]["day"], 60)
        with redirect_stdout(io.StringIO()):
            again.run(10)
        self.assertEqual(again.tick, 70)


if __name__ == "__main__":
    unittest.main()
