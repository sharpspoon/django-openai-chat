from django.conf import settings
from django.http import StreamingHttpResponse
from django.shortcuts import render
from openai import OpenAI, AssistantEventHandler
from typing_extensions import override

# Initialize OpenAI client (set up your API key securely!)
client = OpenAI(api_key=settings.OPENAI_API_KEY)

def assistant_stream_template(request):
    return render(request, "chatapp/assistant_stream.html")

class DjangoEventHandler(AssistantEventHandler):
    def __init__(self, yield_fn):
        super().__init__()           # ← initialize base class so __stream is created
        self.yield_fn = yield_fn

    @override
    def on_event(self, event):
        if event.event == 'thread.run.requires_action':
            run_id = event.data.id
            thread_id = event.data.thread_id
            self.handle_requires_action(event.data, thread_id, run_id)

        elif event.event == 'thread.message.delta':
            # Fix: access .content attribute instead of .get()
            content = event.data.delta.content or ""
            if content:
                self.yield_fn(f"data: {content}\n\n")

        elif event.event == 'thread.run.completed':
            self.yield_fn("data: [DONE]\n\n")

    def handle_requires_action(self, data, thread_id, run_id):
        tool_outputs = []
        for tool in data.required_action.submit_tool_outputs.tool_calls:
            if tool.function.name == "get_current_temperature":
                tool_outputs.append({"tool_call_id": tool.id, "output": "57"})
            elif tool.function.name == "get_rain_probability":
                tool_outputs.append({"tool_call_id": tool.id, "output": "0.06"})
            elif tool.function.name == "import_jira_json":
                tool_outputs.append({"tool_call_id": tool.id, "output": "success"})
        self.submit_tool_outputs(tool_outputs, thread_id, run_id)

    def submit_tool_outputs(self, tool_outputs, thread_id, run_id):
        # Use a FRESH handler!
        new_handler = DjangoEventHandler(self.yield_fn)
        with client.beta.threads.runs.submit_tool_outputs_stream(
            thread_id=thread_id,
            run_id=run_id,
            tool_outputs=tool_outputs,
            event_handler=new_handler,
        ) as stream:
            stream.until_done()

def assistant_stream_view(request):
    prompt = request.GET.get("prompt", "What's the weather?")
    thread = client.beta.threads.create()
    assistant = client.beta.assistants.retrieve(settings.OPENAI_ASSISTANT_ID)

    def event_stream():
        queue = []

        def yield_fn(s): queue.append(s)

        handler = DjangoEventHandler(yield_fn)

        # Add message to thread
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=prompt,
        )

        # Use a FRESH handler instance in the main stream context
        with client.beta.threads.runs.stream(
                thread_id=thread.id,
                assistant_id=assistant.id,
                event_handler=handler,
        ) as stream:
            stream.until_done()

        for s in queue:
            yield s

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
