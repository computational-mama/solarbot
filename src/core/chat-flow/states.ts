import { compact, noop } from "lodash";
import {
  onButtonPressed,
  onButtonReleased,
  onTextInput,
  isButtonDown,
  display,
  getCurrentStatus,
} from "../../device/display";
import {
  recordAudio,
  recordAudioManually,
  recordFileFormat,
  getDynamicVoiceDetectLevel,
} from "../../device/audio";
import { chatWithLLMStream } from "../../cloud-api/server";
import { getSystemPromptWithKnowledge } from "../Knowledge";
import { enableRAG } from "../../cloud-api/knowledge";
import { getLatestGenImg, getLatestDisplayImg } from "../../utils/image";
import { ChatFlowContext, FlowName, FlowStateHandler } from "./types";
import { DEFAULT_EMOJI } from "../../utils";

export const flowStates: Record<FlowName, FlowStateHandler> = {
  sleep: (ctx: ChatFlowContext) => {
    onButtonPressed(() => {
      ctx.transitionTo("listening");
    });
    onButtonReleased(noop);
    onTextInput((text: string) => {
      if (ctx.currentFlowName !== "sleep") return;
      ctx.answerId += 1;
      ctx.asrText = text;
      display({ status: "recognizing", text, text_input_enabled: false });
      ctx.transitionTo("answer");
    });
    display({
      status: "idle",
      emoji: "😴",
      RGB: "#000055",
      rag_icon_visible: false,
      ...(getCurrentStatus().text.endsWith("Listening...") || !getCurrentStatus().text
        ? { text: "Long Press the button to say something." }
        : {}),
    });
  },

  listening: (ctx: ChatFlowContext) => {
    ctx.isFromWakeListening = false;
    ctx.answerId += 1;
    ctx.wakeSessionActive = false;
    ctx.endAfterAnswer = false;
    ctx.currentRecordFilePath = `${ctx.recordingsDir}/user-${Date.now()}.${recordFileFormat}`;
    onButtonPressed(noop);
    const listeningStartedAt = Date.now();
    if (!isButtonDown()) {
      console.log("[listening] Button already released, returning to sleep");
      ctx.transitionTo("sleep");
      return;
    }
    const { result, stop } = recordAudioManually(ctx.currentRecordFilePath);
    onButtonReleased(() => {
      if (Date.now() - listeningStartedAt < 500) {
        stop();
        ctx.transitionTo("sleep");
        return;
      }
      stop();
      display({ RGB: "#ff6800", image: "" });
    });
    result
      .then(() => ctx.transitionTo("asr"))
      .catch((err) => {
        console.error("Error during recording:", err);
        ctx.transitionTo("sleep");
      });
    display({
      status: "listening",
      emoji: DEFAULT_EMOJI,
      RGB: "#00ff00",
      text: "Listening...",
      rag_icon_visible: false,
    });
  },

  wake_listening: (ctx: ChatFlowContext) => {
    ctx.isFromWakeListening = true;
    ctx.answerId += 1;
    ctx.currentRecordFilePath = `${ctx.recordingsDir}/user-${Date.now()}.${recordFileFormat}`;
    onButtonPressed(() => ctx.transitionTo("listening"));
    onButtonReleased(noop);
    display({
      status: "detecting",
      emoji: DEFAULT_EMOJI,
      RGB: "#00ff00",
      text: "Detecting voice level...",
      rag_icon_visible: false,
    });
    getDynamicVoiceDetectLevel().then((level: any) => {
      display({
        status: "listening",
        emoji: DEFAULT_EMOJI,
        RGB: "#00ff00",
        text: `(Detect level: ${level}%) Listening...`,
        rag_icon_visible: false,
      });
      recordAudio(ctx.currentRecordFilePath, ctx.wakeRecordMaxSec, level)
        .then(() => ctx.transitionTo("asr"))
        .catch((err) => {
          console.error("Error during auto recording:", err);
          ctx.endWakeSession();
          ctx.transitionTo("sleep");
        });
    });
  },

  asr: (ctx: ChatFlowContext) => {
    display({ status: "recognizing" });
    Promise.race([
      ctx.recognizeAudio(ctx.currentRecordFilePath, ctx.isFromWakeListening),
      new Promise<string>((resolve) => {
        onButtonPressed(() => resolve("[UserPress]"));
        onButtonReleased(noop);
      }),
    ]).then((result) => {
      if (ctx.currentFlowName !== "asr") return;
      if (result === "[UserPress]") {
        ctx.transitionTo("listening");
        return;
      }
      if (result) {
        console.log("Audio recognized:", result);
        ctx.asrText = result;
        ctx.endAfterAnswer = ctx.shouldEndAfterAnswer(result);
        if (ctx.wakeSessionActive) ctx.wakeSessionLastSpeechAt = Date.now();
        display({ status: "recognizing", text: result });
        ctx.transitionTo("answer");
        return;
      }
      if (ctx.wakeSessionActive) {
        if (ctx.shouldContinueWakeSession()) {
          ctx.transitionTo("wake_listening");
        } else {
          ctx.endWakeSession();
          ctx.transitionTo("sleep");
        }
        return;
      }
      ctx.transitionTo("sleep");
    });
  },

  answer: (ctx: ChatFlowContext) => {
    display({ status: "answering...", RGB: "#00c8a3" });
    const currentAnswerId = ctx.answerId;
    onButtonPressed(() => ctx.transitionTo("listening"));
    onButtonReleased(noop);
    const { partial, endPartial, getPlayEndPromise, stop: stopPlaying } = ctx.streamResponser;
    let llmResponseText = "";
    const trackingPartial = (text: string): void => {
      llmResponseText += text;
      if (currentAnswerId === ctx.answerId) partial(text);
    };
    ctx.partialThinking = "";
    ctx.thinkingSentences = [];
    [() => Promise.resolve().then(() => ""), getSystemPromptWithKnowledge]
    [enableRAG ? 1 : 0](ctx.asrText)
      .then((res: string) => {
        let knowledgePrompt = res;
        if (res && ctx.knowledgePrompts.includes(res)) {
          knowledgePrompt = "";
        }
        if (knowledgePrompt) ctx.knowledgePrompts.push(knowledgePrompt);
        display({ rag_icon_visible: Boolean(enableRAG && knowledgePrompt) });
        const prompt = compact([
          knowledgePrompt ? { role: "system" as const, content: knowledgePrompt } : null,
          { role: "user" as const, content: ctx.asrText },
        ]);
        chatWithLLMStream(
          prompt,
          (text) => { if (currentAnswerId === ctx.answerId) trackingPartial(text); },
          () => currentAnswerId === ctx.answerId && endPartial(),
          (partialThinking) =>
            currentAnswerId === ctx.answerId && ctx.partialThinkingCallback(partialThinking),
          (functionName: string, result?: string) => {
            if (functionName === "endConversation" && result?.startsWith("[success]")) {
              ctx.endAfterAnswer = true;
            }
            if (functionName === "generateImage" && result?.startsWith("[success]")) {
              const img = getLatestGenImg();
              if (img) display({ image: img });
            }
            if (result) {
              display({ text: `[${functionName}]${result}` });
            } else {
              display({ text: `Invoking [${functionName}]... {count}s` });
            }
          },
        );
      });
    getPlayEndPromise().then(() => {
      if (ctx.currentFlowName === "answer") {
        if (ctx.wakeSessionActive || ctx.endAfterAnswer) {
          if (ctx.endAfterAnswer) {
            ctx.endWakeSession();
            ctx.transitionTo("sleep");
          } else {
            ctx.transitionTo("wake_listening");
          }
          return;
        }
        const img = getLatestDisplayImg();
        if (img) {
          ctx.transitionTo("image");
        } else {
          ctx.transitionTo("sleep");
        }
      }
    });
    onButtonPressed(() => {
      stopPlaying();
      ctx.transitionTo("listening");
    });
    onButtonReleased(noop);
  },

  image: (ctx: ChatFlowContext) => {
    onButtonPressed(() => {
      display({ image: "" });
      ctx.transitionTo("listening");
    });
    onButtonReleased(noop);
  },
};
