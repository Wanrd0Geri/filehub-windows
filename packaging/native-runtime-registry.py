from pathlib import Path
import importlib.util,json,sys,time,os
os.environ['QT_QPA_PLATFORM']='windows'
sys.path.insert(0,str(Path('src').resolve()))
from PySide6.QtWidgets import QApplication
from filehub.config import Config,ConfigStore
from filehub.integration import HKCURegistry,MENU_KEYS,RUN_KEY,OWNER
from filehub.ui.app import bootstrap,Runtime,IntegrationController
q=json.loads(Path('sandbox/task6-qa-session.json').read_text());r=Path(q['qa_root']);exe=Path(q['installed'])/'FileHub.exe';assert not list(Path(q['installed']).rglob('opengl32sw.dll'))
reg=HKCURegistry();command=f'"{exe}" --send "%1"';startup=f'"{exe}" --background';before={k:{'owner':reg.get(k,'FileHubOwner'),'command':reg.get(k+'\\command',''),'model':reg.get(k,'MultiSelectModel')} for k in MENU_KEYS};assert all(v=={'owner':OWNER,'command':command,'model':'Player'} for v in before.values());assert reg.get(RUN_KEY,'FileHub')==startup
state=r/'native-runtime-state';sync=r/'native-runtime-sync';(sync/'1_工作/项目/261001_QA_测试').mkdir(parents=True);ConfigStore(state).save(Config(sync_root=sync));app=QApplication([]);rt=Runtime(bootstrap(state),auto_timers=False,integration=IntegrationController(exe),notifier=lambda *x:None,exit_callback=lambda:None)
def settle():
 deadline=time.monotonic()+10
 while rt.window.coordinator.pending and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
 app.processEvents();assert not rt.window.coordinator.pending
settle();assert rt.window.autostart.isChecked() and rt.window.context_menu.isChecked()
rt.window.paused.setChecked(False);rt.window.autostart.setChecked(False);rt.window.context_menu.setChecked(False);rt.window.save_settings();settle();assert not rt.service.config.paused and '运行中' in rt.tray.toolTip();assert reg.get(RUN_KEY,'FileHub') is None and all(not reg.exists(k) for k in MENU_KEYS)
rt.window.paused.setChecked(True);rt.window.autostart.setChecked(True);rt.window.context_menu.setChecked(True);rt.window.save_settings();settle();assert rt.service.config.paused and '暂停' in rt.tray.toolTip();assert reg.get(RUN_KEY,'FileHub')==startup and all(reg.get(k+'\\command','')==command for k in MENU_KEYS)
rt.request_quit();settle();record={'classification':'Windows native source Qt Runtime setting widgets and real HKCU; not installed mouse UI','installer_optional_registration':before,'installer_run':startup,'GUI_setting_off_removed_owned_registration':True,'GUI_setting_on_restored_owned_registration':True,'pause_resume_actual_config_and_tray':True,'Mesa_absent_installed':True};(r/'native-runtime-registry-evidence.json').write_text(json.dumps(record,ensure_ascii=False,indent=2));print(record)
