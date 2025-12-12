import engine_tf


def make(**options):
    options.setdefault('override_tf_cmd', 'terragrunt')
    return engine_tf.make(**options)
