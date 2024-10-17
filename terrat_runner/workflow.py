import collections


Result = collections.namedtuple('Result',
                                [
                                    'success',
                                    'state',
                                    'workflow_step',
                                    'outputs'
                                ])


Result2 = collections.namedtuple('Result2',
                                 [
                                     'payload',
                                     'state',
                                     'step',
                                     'success',
                                 ])
