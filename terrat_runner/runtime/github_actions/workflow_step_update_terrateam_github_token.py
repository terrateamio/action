import api
import workflow


def run(state, config):
    res = api.work_manifest_post(state, 'access-token')

    if res.status_code == 200:
        access_token = res.json()['access_token']
        state.runtime.set_secret(access_token)
        env = state.env.copy()
        env['TERRATEAM_GITHUB_TOKEN'] = access_token
        state = state._replace(env=env)
        return workflow.make(success=True,
                                state=state,
                                step='auth/update-terrateam-github-token',
                                payload={
                                    'visible_on': 'error'
                                })
    else:
        text = """
        Status {}

        {}
        """.format(res.status_code, res.text)
        return workflow.make(success=False,
                                state=state,
                                step='auth/update-terrateam-github-token',
                                payload={
                                    'text': text,
                                    'visible_on': 'error'
                                })
