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
