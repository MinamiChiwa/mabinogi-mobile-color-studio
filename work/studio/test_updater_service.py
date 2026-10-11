import tempfile,unittest
from pathlib import Path
from updater.service import UpdateService


class UpdaterServiceTests(unittest.TestCase):
    def test_busy_session_keeps_update_ready_without_installing(self):
        events=[];calls=[]
        service=UpdateService(lambda event:events.append(event),installer=lambda plan:calls.append(plan))
        service.mark_ready({'version':'0.4.2'})
        service.busy=True
        service.install()
        self.assertEqual(calls,[]);self.assertEqual(service.state,'ready')
        self.assertEqual(events[-1].reason_code,'busy')

    def test_cancel_returns_download_to_available(self):
        service=UpdateService(lambda event:None)
        service.mark_available({'version':'0.4.2'});service.begin_download();service.cancel()
        self.assertEqual(service.state,'available')

    def test_busy_operation_pauses_download_and_does_not_launch_install(self):
        service=UpdateService(lambda event:None)
        service.mark_available({'version':'0.4.3'});service.begin_download()
        service.set_busy(True)
        self.assertTrue(service.cancelled())
        self.assertNotEqual(service.state,'waiting_for_exit')


if __name__=='__main__':unittest.main()
