import unittest

import run_state
import workflow_step_oidc


def make_state(env):
    return run_state.State(
        api_base_url=None,
        api_token=None,
        engine=None,
        env=env,
        outputs=[],
        path=None,
        repo_config={},
        result_version=1,
        runtime=None,
        secrets=set(),
        sha=None,
        success=True,
        tmpdir=None,
        work_manifest={},
        work_token=None,
        workflow=None,
        working_dir=None,
        workspace=None,
    )


class SubstTest(unittest.TestCase):
    def test_replaces_workspace_and_stack_variables(self):
        state = make_state({'TERRATEAM_WORKSPACE': 'production', 'environment': 'production'})
        self.assertEqual(
            workflow_step_oidc._subst(
                state,
                'projects/123/locations/global/workloadIdentityPools/pool-${environment}/providers/github'),
            'projects/123/locations/global/workloadIdentityPools/pool-production/providers/github')
        self.assertEqual(
            workflow_step_oidc._subst(state, 'terrateam-${TERRATEAM_WORKSPACE}@proj.iam.gserviceaccount.com'),
            'terrateam-production@proj.iam.gserviceaccount.com')

    def test_passes_through_non_strings(self):
        state = make_state({})
        self.assertEqual(workflow_step_oidc._subst(state, 3600), 3600)

    def test_unknown_variable_raises_template_error(self):
        state = make_state({})
        with self.assertRaises(workflow_step_oidc.Template_error):
            workflow_step_oidc._subst(state, 'terrateam-${environment}@proj.iam.gserviceaccount.com')

    def test_invalid_placeholder_raises_template_error(self):
        state = make_state({})
        with self.assertRaises(workflow_step_oidc.Template_error):
            workflow_step_oidc._subst(state, 'trailing dollar $')


class RunTemplateErrorTest(unittest.TestCase):
    def test_gcp_unknown_variable_fails_with_actionable_error(self):
        # As in hooks, where TERRATEAM_WORKSPACE and stack variables are not
        # defined.
        state = make_state({})
        config = {
            'type': 'oidc',
            'provider': 'gcp',
            'service_account': 'terrateam-${environment}@proj.iam.gserviceaccount.com',
            'workload_identity_provider': 'projects/123/locations/global/workloadIdentityPools/pool/providers/github',
        }
        result = workflow_step_oidc.run(state, config)
        self.assertFalse(result.success)
        self.assertEqual(result.step, 'auth/oidc')
        self.assertIn('environment', result.payload['text'])
        self.assertIn('terrateam-${environment}@proj.iam.gserviceaccount.com', result.payload['text'])
        self.assertIn('hooks', result.payload['text'])

    def test_aws_unknown_variable_fails_with_actionable_error(self):
        state = make_state({})
        config = {
            'type': 'oidc',
            'provider': 'aws',
            'role_arn': 'arn:aws:iam::123456789012:role/terrateam-${TERRATEAM_WORKSPACE}',
        }
        result = workflow_step_oidc.run(state, config)
        self.assertFalse(result.success)
        self.assertEqual(result.step, 'auth/oidc')
        self.assertIn('TERRATEAM_WORKSPACE', result.payload['text'])


if __name__ == '__main__':
    unittest.main()
