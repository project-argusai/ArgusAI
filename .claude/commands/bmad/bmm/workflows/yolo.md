---
description: 'run create story then story context and if needed code review'
---

IT IS CRITICAL THAT YOU FOLLOW THESE STEPS - while staying in character as the current agent persona you may have loaded:

<steps CRITICAL="TRUE">
1. Always LOAD the FULL @.bmad/core/tasks/workflow.xml
2. READ its entire contents - this is the CORE OS for EXECUTING the specific workflow-config @.bmad/bmm/workflows/4-implementation/create-story/workflow.yaml
3. Pass the yaml path .bmad/bmm/workflows/4-implementation/create-story/workflow.yaml as 'workflow-config' parameter to the workflow.xml instructions
4. Follow workflow.xml instructions EXACTLY as written to process and follow the specific workflow config and its instructions
5. Save outputs after EACH section when generating any documents from templates
</steps>

Once you complete create-story then move to next step

Open a github issue then move to next step

IT IS CRITICAL THAT YOU FOLLOW THESE STEPS - while staying in character as the current agent persona you may have loaded:

<steps CRITICAL="TRUE">
1. Always LOAD the FULL @.bmad/core/tasks/workflow.xml
2. READ its entire contents - this is the CORE OS for EXECUTING the specific workflow-config @.bmad/bmm/workflows/4-implementation/story-context/workflow.yaml
3. Pass the yaml path .bmad/bmm/workflows/4-implementation/story-context/workflow.yaml as 'workflow-config' parameter to the workflow.xml instructions
4. Follow workflow.xml instructions EXACTLY as written to process and follow the specific workflow config and its instructions
5. Save outputs after EACH section when generating any documents from templates
</steps>

Once you complete story-context then move to next step

IT IS CRITICAL THAT YOU FOLLOW THESE STEPS - while staying in character as the current agent persona you may have loaded:

<steps CRITICAL="TRUE">
1. Always LOAD the FULL @.bmad/core/tasks/workflow.xml
2. READ its entire contents - this is the CORE OS for EXECUTING the specific workflow-config @.bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml
3. Pass the yaml path .bmad/bmm/workflows/4-implementation/dev-story/workflow.yaml as 'workflow-config' parameter to the workflow.xml instructions
4. Follow workflow.xml instructions EXACTLY as written to process and follow the specific workflow config and its instructions
5. Save outputs after EACH section when generating any documents from templates
</steps>

Once you complete dev-story then move to next step and only if status says a review is needed

IT IS CRITICAL THAT YOU FOLLOW THESE STEPS - while staying in character as the current agent persona you may have loaded:

<steps CRITICAL="TRUE">
1. Always LOAD the FULL @.bmad/core/tasks/workflow.xml
2. READ its entire contents - this is the CORE OS for EXECUTING the specific workflow-config @.bmad/bmm/workflows/4-implementation/code-review/workflow.yaml
3. Pass the yaml path .bmad/bmm/workflows/4-implementation/code-review/workflow.yaml as 'workflow-config' parameter to the workflow.xml instructions
4. Follow workflow.xml instructions EXACTLY as written to process and follow the specific workflow config and its instructions
5. Save outputs after EACH section when generating any documents from templates
</steps>

Once complete commit and and push. Look up the github issue link in the backlog or sprint-status documents. create a pull request tying this to the appropriate github issue. Close out the github issue.
