import { useEffect, useState } from "react";
import { Check, PlugZap, Save, ShieldCheck } from "lucide-react";
import { api } from "../api";
import { networkMessage } from "../utils";

const providers = [
  {
    name: "DeepSeek",
    base_url: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
  },
  {
    name: "Kimi",
    base_url: "https://api.moonshot.cn/v1",
    model: "moonshot-v1-8k",
  },
  {
    name: "通义千问",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
  },
  {
    name: "OpenAI",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
  },
];
export default function SettingsPage() {
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [configured, setConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api
      .settings()
      .then((config) => {
        if (active) {
          setBaseUrl(config.base_url);
          setModel(config.model);
          setConfigured(config.api_key_configured);
        }
      })
      .catch((error) => {
        if (active) setError(networkMessage(error));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [retry]);
  function input() {
    return {
      base_url: baseUrl.trim(),
      model: model.trim(),
      ...(key.trim() ? { api_key: key.trim() } : {}),
    };
  }
  async function act(action: "save" | "test") {
    setBusy(action);
    setError("");
    setNotice("");
    try {
      if (action === "save") {
        const result = await api.saveSettings(input());
        setConfigured(result.api_key_configured);
        setKey("");
        setNotice("已保存");
      } else {
        const result = await api.testSettings(input());
        if (result.success) setNotice(result.message);
        else setError(`${result.error_type}：${result.message}`);
      }
    } catch (error) {
      setError(networkMessage(error));
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="settings-page">
      <span className="eyebrow">BRING YOUR OWN AI</span>
      <h1 className="page-title">
        你的 AI，你来选<span className="accent">。</span>
      </h1>
      <p className="page-subtitle">
        连接任意 OpenAI 兼容云端服务。配置保存在这台电脑，密钥不会随应用分发。
      </p>
      <form
        className="settings-panel"
        onSubmit={(event) => {
          event.preventDefault();
          void act("save");
        }}
      >
        <fieldset disabled={loading || !!busy}>
          <label className="field-label" htmlFor="base-url">
            API 地址 <span className="muted font-normal ml-2">base_url</span>
          </label>
          <input
            id="base-url"
            className="field-input"
            value={baseUrl}
            type="url"
            required
            placeholder="https://api.deepseek.com/v1"
            onChange={(event) => {
              setBaseUrl(event.target.value);
              setNotice("");
            }}
          />
          <p className="field-hint">
            选择常见厂商，一键填入地址与模型；也支持你自己的中转地址。
          </p>
          <div className="provider-list">
            {providers.map((provider) => (
              <button
                type="button"
                className="provider-chip"
                key={provider.name}
                onClick={() => {
                  setBaseUrl(provider.base_url);
                  setModel(provider.model);
                  setNotice("");
                  setError("");
                }}
              >
                {provider.name}
              </button>
            ))}
          </div>
          <label className="field-label" htmlFor="api-key">
            API Key{" "}
            <span className="muted font-normal ml-2">
              {configured ? "已配置" : "未配置"}
            </span>
          </label>
          <input
            id="api-key"
            className="field-input"
            type="password"
            autoComplete="new-password"
            value={key}
            placeholder={
              configured ? "已安全保存，留空表示不修改" : "粘贴你自己的 API Key"
            }
            onChange={(event) => {
              setKey(event.target.value);
              setNotice("");
            }}
          />
          <p className="field-hint mb-6">
            密钥只传给本地后端保存，不会在读取设置时返回明文。
          </p>
          <label className="field-label" htmlFor="model">
            模型名称 <span className="muted font-normal ml-2">model</span>
          </label>
          <input
            id="model"
            className="field-input"
            value={model}
            required
            placeholder="deepseek-chat"
            onChange={(event) => {
              setModel(event.target.value);
              setNotice("");
            }}
          />
          <p className="field-hint">
            示例：deepseek-chat / moonshot-v1-8k / qwen-plus /
            gpt-4o-mini。以厂商账号可用模型为准。
          </p>
          <div className="flex gap-3 mt-7 flex-wrap">
            <button type="submit" className="button primary">
              <Save size={17} />
              {busy === "save" ? "保存中…" : "保存配置"}
            </button>
            <button
              type="button"
              className="button secondary"
              disabled={!baseUrl.trim() || !model.trim()}
              onClick={() => void act("test")}
            >
              <PlugZap size={17} />
              {busy === "test" ? "连接测试中…" : "测试连接"}
            </button>
          </div>
        </fieldset>
        {loading && (
          <p className="muted text-sm mt-4" role="status">
            正在读取本机配置…
          </p>
        )}
        {error && (
          <div className="error-message mt-5" role="alert">
            {error}
            <button
              type="button"
              className="text-link ml-3"
              onClick={() => setRetry((value) => value + 1)}
            >
              重新读取
            </button>
          </div>
        )}
        {notice && (
          <div
            className="success-message mt-5 flex gap-2 items-center"
            role="status"
          >
            <Check size={17} />
            {notice}
          </div>
        )}
        <div className="privacy-note mt-7">
          <ShieldCheck size={18} className="shrink-0" />
          <p>
            生成知识卡时，提取的课件文字会发送到上述服务。原始 PDF/PPTX
            不会上传到 AI 服务。API 的使用额度和费用由你与厂商结算。
          </p>
        </div>
      </form>
    </div>
  );
}
