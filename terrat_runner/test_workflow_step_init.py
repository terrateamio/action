import unittest
from types import SimpleNamespace

import workflow_step_init


class InitStepTest(unittest.TestCase):
    def _visible_on_of_run(self, config):
        engine = SimpleNamespace(
            init=lambda _state, _config: (True, 'stdout', ''),
            name='tf',
        )
        state = SimpleNamespace(engine=engine)

        return workflow_step_init.run(state, config).payload['visible_on']

    def test_run_defaults_visible_on_to_failure(self):
        self.assertEqual(self._visible_on_of_run({}), 'failure')

    def test_run_takes_visible_on_from_the_step_config(self):
        self.assertEqual(self._visible_on_of_run({'visible_on': 'always'}), 'always')


if __name__ == '__main__':
    unittest.main()
