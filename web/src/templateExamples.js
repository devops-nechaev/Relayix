// Examples are editable drafts. Nothing is inserted into the database automatically.
export const templateExamples=[
 {label:'Simple message',name:'Example message',title:'{{title}}',body:'{{message}}',payload:{title:'Example notification',message:'An example message from your application.'}},
 {label:'Test results',name:'Example test results',title:'{{test_type}} {{suite}}',body:'Branch: {{branch}}\n\nStatus: {{status}}\nFailed: {{failed}}\nPassed: {{passed}}\nSkipped: {{skipped}}',link_label:'Runner log',link_url:'{{log_url}}',link_failure_only:true,payload:{test_type:'UnitTests',suite:'ExampleSuite',branch:'feature/example-tests',status:'❌',failed:2,passed:40,skipped:0,log_url:'https://gitlab.example.org/acme/demo/-/jobs/12345'}},
 {label:'Deployment',name:'Example deployment',title:'Deploy · {{project}}',body:'{{message}}\n\n**Project:** {{project}}\n**Branch:** {{branch}}\n[Pipeline]({{pipeline_url}})',payload:{message:'✅ Deployment completed',project:'ExampleService',branch:'release/example',pipeline_url:'https://gitlab.example.org/acme/demo/-/pipelines/42'}}
];
