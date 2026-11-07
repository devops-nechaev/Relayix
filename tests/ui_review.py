"""Focused UI regression checks with fictional API responses; no live deliveries.

Run in the browser test image with RELAYIX_REVIEW_DIST and RELAYIX_REVIEW_OUT
pointing at the built web directory and screenshot output directory.
"""
import functools
import http.server
import json
import os
import re
from pathlib import Path
import threading
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

root=Path(os.environ['RELAYIX_REVIEW_DIST'])
out=Path(os.environ['RELAYIX_REVIEW_OUT']);out.mkdir(parents=True,exist_ok=True)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(root)))
threading.Thread(target=server.serve_forever,daemon=True).start()
base=f'http://127.0.0.1:{server.server_port}'
preferences={'tables':{},'refresh_interval_seconds':0}
channel={'id':'channel-demo','name':'Operations','kind':'webhook','config':{'url':'https://example.org/hook'},'enabled':True}
route={'id':'route-demo','name':'Production','slug':'production','channels':[channel['id']],'fallback_channel_ids':[],'enabled':True,'min_priority':1,'required_tag':'','icon':'git-branch'}
recipient={'id':'delivery-demo','channel_id':channel['id'],'channel_name':channel['name'],'channel_kind':'webhook','status':'failed','attempts':5,'error':'HTTP 503','is_fallback':False}
event={'id':'event-demo','event_id':'event-demo','route_id':route['id'],'route_name':route['name'],'route_icon':'git-branch','created_at':'2026-11-07T10:00:00Z','title':'Deploy ExampleService','has_title':True,'message':'Deployment complete','priority':3,'tags':['deploy'],'recipients':[recipient],'routing':{'reason':'queued','route_enabled':True,'priority':3,'min_priority':1,'priority_match':True,'active_destinations':1,'destinations':1},'original_payload':{'message':'Deployment complete'},'rendered_payload':{'message':'Deployment complete'},'template':None,'template_result':None,'deliveries':1,'sent':0}
with sync_playwright() as p:
 browser=p.chromium.launch()
 page=browser.new_page(viewport={'width':1680,'height':1100},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
 def api(request):
  global preferences
  path=urlsplit(request.request.url).path
  if path=='/api/auth/preferences' and request.request.method=='PUT':preferences=request.request.post_data_json;data=preferences
  elif path=='/api/auth/me':data={'id':'user-demo','username':'demo','display_name':'Demo user','role':'admin','preferences':preferences}
  elif path=='/api/channels':data=[channel]
  elif path=='/api/routes':data=[route]
  elif path=='/api/templates' or path=='/api/tags':data=[]
  elif path=='/api/stats':data={'total':1,'sent':0,'failed':1,'pending':0,'retrying':0}
  elif path in ('/api/deliveries','/api/events'):data={'items':[event],'total':1,'page':1,'page_size':50}
  elif path=='/api/events/event-demo':data=event
  else:raise AssertionError(f'Unexpected API call: {path}')
  request.fulfill(json=data)
 page.route('**/api/**',api)
 page.goto(base)
 recent=page.get_by_role('table',name='Recent deliveries',exact=True)
 expect(recent).to_be_visible()
 toolbar=page.locator('.table-tools.panel-heading')
 columns=toolbar.locator('summary').bounding_box();view=toolbar.get_by_role('button',name='View all').bounding_box()
 assert abs(columns['y']-view['y'])<3
 assert set(page.locator('.view-all').evaluate_all('(nodes)=>nodes.map(n=>n.className)'))=={'view-all'}
 page.screenshot(path=str(out/'dashboard-updated.png'),full_page=True)
 menu=toolbar.locator('.column-menu');menu.locator('summary').click()
 menu.get_by_role('button',name='Move Notification column left',exact=True).click()
 expect(recent.locator('th').first).to_contain_text('Notification')
 assert preferences['tables']['dashboard_deliveries']['column_order'][0]=='title'
 menu.get_by_label('Show Tags column',exact=True).uncheck()
 expect(recent.get_by_role('columnheader',name='Tags',exact=True)).to_have_count(0)
 # Drag is a second, independent path to the same durable order setting.
 menu.locator('.column-option').filter(has_text='Route').drag_to(menu.locator('.column-option').filter(has_text='Notification'))
 expect(recent.locator('th').first).to_contain_text('Route')
 page.keyboard.press('Escape');page.reload()
 expect(recent.locator('th').first).to_contain_text('Route')
 expect(recent.get_by_role('columnheader',name='Tags',exact=True)).to_have_count(0)
 recent.get_by_role('button',name='Details',exact=True).click()
 drawer=page.get_by_role('dialog',name='Event details',exact=True)
 expect(drawer.get_by_role('tab',name='Overview',exact=True)).to_be_visible()
 drawer.get_by_role('tab',name='Technical',exact=True).click()
 expect(drawer.get_by_text('Original payload',exact=True)).to_be_visible()
 page.screenshot(path=str(out/'delivery-event-details.png'),full_page=True)
 drawer.get_by_role('button',name='Close dialog',exact=True).click()
 dashboard_actions=page.locator('.compact-item').first.locator('.actions button').all_text_contents()
 page.locator('nav').get_by_role('button',name='Channels',exact=True).click()
 assert page.locator('.channel-card .actions button').all_text_contents()==dashboard_actions
 page.locator('nav').get_by_role('button',name='Templates',exact=True).click()
 expect(page.locator('.template-example-actions button')).to_have_count(5)
 expect(page.get_by_role('button',name='Use Service incident example',exact=True)).to_have_count(0)
 page.get_by_role('button',name='Use Backup report example',exact=True).click()
 sample_editor=page.get_by_role('dialog',name='Create template',exact=True)
 expect(sample_editor.get_by_label('Template name',exact=True)).to_have_value('Example backup report')
 sample=json.loads(sample_editor.get_by_label('Example incoming JSON',exact=True).input_value())
 assert sample['backup_size']=='2.4 GB'
 sample_editor.get_by_role('button',name='Cancel',exact=True).click()
 page.get_by_role('button',name='Create template',exact=True).click()
 editor=page.get_by_role('dialog',name='Create template',exact=True)
 library=editor.get_by_role('region',name='Template field library')
 expect(library.get_by_role('button',name='Message 4',exact=True)).to_be_visible()
 expect(library.get_by_role('button',name=re.compile(r'^Monitoring'))).to_have_count(0)
 library.get_by_role('button',name='Tests 7',exact=True).click()
 expect(library.locator('.field-option')).to_have_count(7)
 editor.get_by_label('Example incoming JSON',exact=True).fill('{"status":"Failed","custom":{"owner":"Demo"}}')
 title=editor.get_by_label('Title (optional)',exact=True);title.fill('Build: ');title.focus()
 library.locator('.field-option').filter(has=page.locator('code',has_text='{{status}}')).click()
 expect(title).to_have_value('Build: {{status}}')
 expect(title).to_be_focused()
 page.screenshot(path=str(out/'template-fields-cards.png'),full_page=True)
 library.get_by_role('button',name='Compact field list',exact=True).click()
 page.screenshot(path=str(out/'template-fields-list.png'),full_page=True)
 title.fill('prefix suffix');title.focus();title.evaluate('(element)=>element.setSelectionRange(7,7)')
 library.locator('.field-option').filter(has=page.locator('code',has_text='{{suite}}')).click()
 expect(title).to_have_value('prefix {{suite}}suffix')
 library.get_by_role('button',name=re.compile(r'^All \d+$')).click()
 expect(library.locator('.field-option')).to_have_count(26)
 expect(library.locator('.field-option').filter(has=page.locator('code',has_text='{{status}}'))).to_have_count(1)
 expect(library.locator('.field-option').filter(has=page.locator('code',has_text='{{message}}'))).to_be_visible()
 expect(library.locator('.field-option').filter(has_text='custom.owner')).to_be_visible()
 library.get_by_label('Search template fields',exact=True).fill('pipeline')
 expect(library.locator('.field-option')).to_have_count(1)
 # Small screens keep the page and editor inside the viewport.
 page.set_viewport_size({'width':390,'height':844})
 assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
 editor.get_by_role('button',name='Cancel',exact=True).click()
 page.get_by_role('button',name='Create template',exact=True).click()
 library.locator('.field-option').filter(has=page.locator('code',has_text='{{message}}')).click()
 expect(editor.get_by_label('Message template',exact=True)).to_have_value('{{message}}')
 expect(editor.get_by_label('Title (optional)',exact=True)).to_have_value('')
 editor.get_by_role('button',name='Cancel',exact=True).click()
 page.locator('nav').get_by_role('button',name='Dashboard',exact=True).click()
 expect(recent).to_be_visible()
 assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
 page.screenshot(path=str(out/'dashboard-mobile.png'),full_page=True)
 assert not errors,errors
 browser.close()
server.shutdown()
print('PASS: column drag/arrows, persistence, hiding, shared toolbar/actions, event drawer, template categories/search/cursor insertion, desktop/mobile layout')
