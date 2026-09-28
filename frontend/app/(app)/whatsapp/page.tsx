"use client";

import { useEffect, useState } from "react";
import {
  api, WhatsAppConfig, WhatsAppConversation, WhatsAppMessage
} from "@/lib/api";

export default function WhatsAppPage() {
  const [activeTab, setActiveTab] = useState<"chats" | "settings">("chats");
  
  // Conversations & Messages State
  const [conversations, setConversations] = useState<WhatsAppConversation[]>([]);
  const [selectedPhone, setSelectedPhone] = useState<string | null>(null);
  const [messages, setMessages] = useState<WhatsAppMessage[]>([]);
  const [textInput, setTextInput] = useState("");
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [newChatPhone, setNewChatPhone] = useState("");
  const [showNewChatModal, setShowNewChatModal] = useState(false);

  // Settings State
  const [config, setConfig] = useState<WhatsAppConfig | null>(null);
  const [saveLoading, setSaveLoading] = useState(false);
  const [configSuccess, setConfigSuccess] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (!selectedPhone) return;

    let cancelled = false;

    const refreshWhatsApp = async () => {
      try {
        const [msgs, convs] = await Promise.all([
          api.getWhatsAppMessages(selectedPhone),
          api.listWhatsAppConversations(),
        ]);

        if (cancelled) return;

        setMessages(msgs);
        setConversations(convs);
      } catch (err) {
        // Do not break the chat UI if one background refresh fails.
        console.error("WhatsApp background refresh failed:", err);
      }
    };

    // Load immediately when a conversation is selected.
    refreshWhatsApp();

    // Keep the active conversation synchronized with the backend.
    const intervalId = window.setInterval(refreshWhatsApp, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [selectedPhone]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [convs, cfg] = await Promise.all([
        api.listWhatsAppConversations(),
        api.getWhatsAppConfig()
      ]);
      setConversations(convs);
      setConfig(cfg);
      if (convs.length > 0 && !selectedPhone) {
        setSelectedPhone(convs[0].customer_phone);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load WhatsApp data");
    } finally {
      setLoading(false);
    }
  };

  const loadMessages = async (phone: string) => {
    try {
      const msgs = await api.getWhatsAppMessages(phone);
      setMessages(msgs);
    } catch (err: any) {
      console.error("Failed to load messages", err);
    }
  };

  const handleSendMessage = async () => {
    if (!selectedPhone || !textInput.trim() || isSending) return;
    setIsSending(true);
    try {
      await api.sendWhatsAppMessage({
        recipient_phone: selectedPhone,
        message_text: textInput.trim()
      });
      setTextInput("");
      await loadMessages(selectedPhone);
      const updatedConvs = await api.listWhatsAppConversations();
      setConversations(updatedConvs);
    } catch (err: any) {
      alert("Error sending WhatsApp message: " + err.message);
    } finally {
      setIsSending(false);
    }
  };

  const handleSuggestAiReply = async () => {
    if (!selectedPhone || isSuggesting) return;
    setIsSuggesting(true);
    try {
      const lastInbound = messages.filter(m => m.direction === "inbound").pop()?.body || "Hello";
      const res = await api.suggestWhatsAppAiReply({
        recipient_phone: selectedPhone,
        incoming_text: lastInbound
      });
      setTextInput(res.suggested_reply);
    } catch (err: any) {
      alert("Failed to generate AI suggestion: " + err.message);
    } finally {
      setIsSuggesting(false);
    }
  };

  const handleStartNewChat = () => {
    if (!newChatPhone.trim()) return;
    const clean = newChatPhone.trim();
    setSelectedPhone(clean);
    setShowNewChatModal(false);
    setNewChatPhone("");
    setMessages([]);
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!config) return;
    setSaveLoading(true);
    setConfigSuccess(false);
    try {
      await api.updateWhatsAppConfig(config);
      setConfigSuccess(true);
      setTimeout(() => setConfigSuccess(false), 4000);
    } catch (err: any) {
      alert("Failed to save settings: " + err.message);
    } finally {
      setSaveLoading(false);
    }
  };

  const activeConv = conversations.find(c => c.customer_phone === selectedPhone);

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-gradient-to-r from-emerald-600 to-teal-700 p-6 rounded-2xl text-white shadow-lg">
        <div>
          <div className="flex items-center gap-2">
            <span className="bg-white/20 text-white text-xs font-semibold px-2.5 py-1 rounded-full uppercase tracking-wider">
              Integration Ready
            </span>
            {config?.auto_reply_enabled && (
              <span className="bg-emerald-400/30 text-emerald-100 text-xs font-semibold px-2 py-0.5 rounded-full flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-300 animate-pulse"></span>
                AI Auto-Reply Active
              </span>
            )}
          </div>
          <h1 className="text-2xl font-bold mt-2">AI WhatsApp Assistant</h1>
          <p className="text-emerald-100 text-sm mt-1">
            Meta WhatsApp Business Cloud API integration, instant customer chat support, PDF document delivery, and automated AI workflows.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex bg-emerald-800/40 p-1.5 rounded-xl border border-white/10 self-start sm:self-auto">
          <button
            onClick={() => setActiveTab("chats")}
            className={`px-4 py-2 text-sm font-semibold rounded-lg transition-all ${
              activeTab === "chats"
                ? "bg-white text-emerald-900 shadow"
                : "text-white/80 hover:text-white"
            }`}
          >
            💬 Inbox & Live Chats
          </button>
          <button
            onClick={() => setActiveTab("settings")}
            className={`px-4 py-2 text-sm font-semibold rounded-lg transition-all ${
              activeTab === "settings"
                ? "bg-white text-emerald-900 shadow"
                : "text-white/80 hover:text-white"
            }`}
          >
            ⚙️ Meta API & AI Settings
          </button>
        </div>
      </div>

      {loading ? (
        <div className="p-12 text-center text-slate-500 bg-white rounded-xl border border-slate-200">
          <div className="inline-block animate-spin w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full mb-3"></div>
          <p className="font-medium">Loading WhatsApp Workspace...</p>
        </div>
      ) : error ? (
        <div className="p-6 bg-red-50 text-red-700 rounded-xl border border-red-200">
          <p className="font-bold">Error loading WhatsApp module</p>
          <p className="text-sm mt-1">{error}</p>
        </div>
      ) : activeTab === "chats" ? (
        /* CHATS TAB */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden min-h-[620px]">
          
          {/* Left Panel: Conversation List */}
          <div className="border-r border-slate-200 flex flex-col bg-slate-50/50">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-white">
              <h2 className="font-bold text-slate-800">Conversations</h2>
              <button
                onClick={() => setShowNewChatModal(true)}
                className="px-3 py-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition shadow-sm"
              >
                + New Chat
              </button>
            </div>

            <div className="overflow-y-auto flex-1 divide-y divide-slate-100">
              {conversations.length === 0 ? (
                <div className="p-6 text-center text-slate-400 text-sm">
                  No conversations yet. Click <strong>+ New Chat</strong> or receive a WhatsApp message to start.
                </div>
              ) : (
                conversations.map((conv) => {
                  const isSelected = conv.customer_phone === selectedPhone;
                  return (
                    <button
                      key={conv.id}
                      onClick={() => setSelectedPhone(conv.customer_phone)}
                      className={`w-full text-left p-4 transition flex items-start gap-3 ${
                        isSelected ? "bg-emerald-50/80 border-l-4 border-emerald-600" : "hover:bg-slate-100/70"
                      }`}
                    >
                      <div className="w-10 h-10 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold shrink-0">
                        {conv.customer_name?.[0]?.toUpperCase() || "W"}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <p className="font-semibold text-sm text-slate-900 truncate">{conv.customer_name}</p>
                          {conv.unread_count > 0 && (
                            <span className="bg-emerald-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                              {conv.unread_count}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-500 truncate">{conv.customer_phone}</p>
                        <p className="text-xs text-slate-600 truncate mt-1">{conv.last_message_preview || "No messages"}</p>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Panel: Chat Stream */}
          <div className="lg:col-span-2 flex flex-col bg-white">
            {selectedPhone ? (
              <>
                {/* Chat Top Bar */}
                <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold">
                      {activeConv?.customer_name?.[0]?.toUpperCase() || "W"}
                    </div>
                    <div>
                      <h3 className="font-bold text-slate-800">{activeConv?.customer_name || selectedPhone}</h3>
                      <p className="text-xs text-slate-500">{selectedPhone}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-1 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      LIVE
                    </span>
                    <button
                      onClick={() => loadMessages(selectedPhone)}
                      className="text-xs text-slate-500 hover:text-slate-800 bg-white border border-slate-200 px-3 py-1.5 rounded-lg"
                    >
                      🔄 Refresh
                    </button>
                  </div>
                </div>

                {/* Message Bubble Feed */}
                <div className="flex-1 p-4 overflow-y-auto space-y-3 bg-slate-50/30 min-h-[400px]">
                  {messages.length === 0 ? (
                    <div className="text-center text-slate-400 text-sm my-12">
                      Start typing below or use <strong>✨ AI Draft Reply</strong> to write a message.
                    </div>
                  ) : (
                    messages.map((m) => {
                      const isInbound = m.direction === "inbound";
                      return (
                        <div
                          key={m.id}
                          className={`flex flex-col ${isInbound ? "items-start" : "items-end"}`}
                        >
                          <div
                            className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm shadow-sm ${
                              isInbound
                                ? "bg-white text-slate-800 border border-slate-200 rounded-tl-none"
                                : "bg-emerald-600 text-white rounded-tr-none"
                            }`}
                          >
                            <p className="whitespace-pre-wrap">{m.body}</p>
                            {m.ai_generated && (
                              <span className="mt-1 inline-block text-[10px] bg-white/20 text-white px-1.5 py-0.5 rounded font-medium">
                                ✨ AI Auto-Generated
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-slate-400 mt-1 px-1">
                            {m.created_at ? new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ""} • {m.status}
                          </span>
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Bottom Input Area */}
                <div className="p-4 border-t border-slate-200 bg-white space-y-3">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleSuggestAiReply}
                      disabled={isSuggesting}
                      className="px-3 py-1.5 text-xs font-semibold bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white rounded-lg transition flex items-center gap-1.5 disabled:opacity-50"
                    >
                      {isSuggesting ? "Generating..." : "✨ AI Draft Reply"}
                    </button>
                  </div>
                  <div className="flex gap-2">
                    <textarea
                      rows={2}
                      value={textInput}
                      onChange={(e) => setTextInput(e.target.value)}
                      placeholder="Type your WhatsApp message..."
                      className="flex-1 p-3 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 resize-none"
                    />
                    <button
                      onClick={handleSendMessage}
                      disabled={isSending || !textInput.trim()}
                      className="px-5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-xl text-sm transition disabled:opacity-50 flex items-center justify-center shrink-0"
                    >
                      {isSending ? "Sending..." : "Send 🚀"}
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="p-12 text-center text-slate-400 my-auto">
                Select a conversation on the left to start chatting.
              </div>
            )}
          </div>
        </div>
      ) : (
        /* SETTINGS TAB */
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm max-w-3xl">
          <h2 className="text-xl font-bold text-slate-800 mb-1">Meta WhatsApp Cloud API Configuration</h2>
          <p className="text-sm text-slate-500 mb-6">
            Configure your Meta Business App credentials to connect live WhatsApp numbers, or leave credentials blank to run in simulated mode.
          </p>

          {configSuccess && (
            <div className="mb-6 p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-sm font-semibold flex items-center gap-2">
              ✅ WhatsApp Settings updated successfully!
            </div>
          )}

          <form onSubmit={handleSaveConfig} className="space-y-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">Phone Number ID</label>
                <input
                  type="text"
                  value={config?.phone_number_id || ""}
                  onChange={(e) => setConfig({ ...config!, phone_number_id: e.target.value })}
                  placeholder="e.g. 109876543210123"
                  className="w-full p-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-emerald-500"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase mb-1">WABA ID (Account ID)</label>
                <input
                  type="text"
                  value={config?.waba_id || ""}
                  onChange={(e) => setConfig({ ...config!, waba_id: e.target.value })}
                  placeholder="e.g. 987654321012345"
                  className="w-full p-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-emerald-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase mb-1">Meta Permanent System Access Token</label>
              <input
                type="password"
                value={config?.access_token || ""}
                onChange={(e) => setConfig({ ...config!, access_token: e.target.value })}
                placeholder="EAAG..."
                className="w-full p-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
              <label className="block text-xs font-bold text-slate-700 uppercase mb-1">Webhook Verify Token</label>
              <input
                type="text"
                value={config?.verify_token || "ai_employee_os_token"}
                onChange={(e) => setConfig({ ...config!, verify_token: e.target.value })}
                className="w-full p-2.5 bg-white border border-slate-200 rounded-lg text-sm"
              />
              <p className="text-xs text-slate-500 mt-2">
                Use this token when configuring your Meta Webhook URL: <code className="bg-slate-200 px-1.5 py-0.5 rounded text-slate-800">{config?.webhook_url || "/api/whatsapp/webhook"}</code>
              </p>
            </div>

            <div className="pt-2 border-t border-slate-100">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-slate-800 text-sm">AI Auto-Reply Mode</h3>
                  <p className="text-xs text-slate-500">Automatically answer incoming WhatsApp customer queries using OpenAI</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config?.auto_reply_enabled || false}
                    onChange={(e) => setConfig({ ...config!, auto_reply_enabled: e.target.checked })}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
                </label>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase mb-1">AI Assistant Custom Instructions</label>
              <textarea
                rows={3}
                value={config?.ai_instructions || ""}
                onChange={(e) => setConfig({ ...config!, ai_instructions: e.target.value })}
                placeholder="e.g. We are open Mon-Fri 9am-6pm. For urgent technical queries ask them to call 0300-1234567."
                className="w-full p-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <button
              type="submit"
              disabled={saveLoading}
              className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl transition shadow disabled:opacity-50"
            >
              {saveLoading ? "Saving..." : "Save Settings"}
            </button>
          </form>
        </div>
      )}

      {/* New Chat Modal */}
      {showNewChatModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <h3 className="text-lg font-bold text-slate-800">Start New WhatsApp Chat</h3>
            <p className="text-xs text-slate-500">Enter customer phone number with country code (e.g. +923001234567)</p>
            <input
              type="text"
              value={newChatPhone}
              onChange={(e) => setNewChatPhone(e.target.value)}
              placeholder="+923001234567"
              className="w-full p-3 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-emerald-500"
            />
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowNewChatModal(false)}
                className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-xl"
              >
                Cancel
              </button>
              <button
                onClick={handleStartNewChat}
                className="px-4 py-2 text-sm font-bold bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl"
              >
                Start Chat
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
