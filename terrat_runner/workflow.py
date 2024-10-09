import collections


Result = collections.namedtuple('Result',
                                [
                                    'success',
                                    'state',
                                    'workflow_step',
                                    'outputs'
                                ])
