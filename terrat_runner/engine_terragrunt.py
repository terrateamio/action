import engine_tf


def make(**options):
    options['tf_cmd'] = 'terragrunt'
    return engine_tf.make(**options)
