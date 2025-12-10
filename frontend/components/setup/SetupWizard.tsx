/**
 * Setup Wizard Component
 * First-run setup wizard for configuring the application
 * FF-008: Installation Script & Setup Wizard
 */

'use client';

import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import {
  CheckCircle2,
  Circle,
  Loader2,
  Brain,
  Shield,
  Video,
  Settings,
  ArrowRight,
  ArrowLeft,
  ExternalLink,
  Eye,
  EyeOff,
  Check,
  X,
  AlertTriangle,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';

import { apiClient } from '@/lib/api-client';
import type { AIProvider } from '@/types/settings';

interface SetupStep {
  id: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  required: boolean;
}

const SETUP_STEPS: SetupStep[] = [
  {
    id: 'welcome',
    title: 'Welcome',
    description: 'Get started with Live Object AI Classifier',
    icon: <Settings className="h-5 w-5" />,
    required: true,
  },
  {
    id: 'ai',
    title: 'AI Provider',
    description: 'Configure at least one AI provider',
    icon: <Brain className="h-5 w-5" />,
    required: true,
  },
  {
    id: 'camera',
    title: 'Camera Source',
    description: 'Add your first camera (optional)',
    icon: <Video className="h-5 w-5" />,
    required: false,
  },
  {
    id: 'protect',
    title: 'UniFi Protect',
    description: 'Connect UniFi Protect controller (optional)',
    icon: <Shield className="h-5 w-5" />,
    required: false,
  },
  {
    id: 'complete',
    title: 'Complete',
    description: 'Setup complete!',
    icon: <CheckCircle2 className="h-5 w-5" />,
    required: true,
  },
];

interface AIProviderConfig {
  provider: AIProvider;
  name: string;
  description: string;
  placeholder: string;
  docsUrl: string;
}

const AI_PROVIDERS: AIProviderConfig[] = [
  {
    provider: 'openai',
    name: 'OpenAI',
    description: 'GPT-4o mini - Best cost/quality ratio (recommended)',
    placeholder: 'sk-...',
    docsUrl: 'https://platform.openai.com/api-keys',
  },
  {
    provider: 'grok',
    name: 'xAI Grok',
    description: 'Grok 2 Vision - Fast vision analysis',
    placeholder: 'xai-...',
    docsUrl: 'https://console.x.ai',
  },
  {
    provider: 'anthropic',
    name: 'Anthropic Claude',
    description: 'Claude 3 Haiku - Reliable fallback',
    placeholder: 'sk-ant-...',
    docsUrl: 'https://console.anthropic.com',
  },
  {
    provider: 'google',
    name: 'Google Gemini',
    description: 'Gemini Flash - Free tier available',
    placeholder: 'AIza...',
    docsUrl: 'https://aistudio.google.com/apikey',
  },
];

interface SetupWizardProps {
  onComplete: () => void;
}

export function SetupWizard({ onComplete }: SetupWizardProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set());

  // AI Provider state
  const [aiKeys, setAiKeys] = useState<Record<AIProvider, string>>({
    openai: '',
    grok: '',
    anthropic: '',
    google: '',
  });
  const [showKeys, setShowKeys] = useState<Record<AIProvider, boolean>>({
    openai: false,
    grok: false,
    anthropic: false,
    google: false,
  });
  const [testingProvider, setTestingProvider] = useState<AIProvider | null>(null);
  const [testedProviders, setTestedProviders] = useState<Record<AIProvider, 'success' | 'error' | null>>({
    openai: null,
    grok: null,
    anthropic: null,
    google: null,
  });
  const [savingProvider, setSavingProvider] = useState<AIProvider | null>(null);
  const [configuredProviders, setConfiguredProviders] = useState<Set<AIProvider>>(new Set());

  // Load existing AI provider status on mount
  useEffect(() => {
    loadAIProvidersStatus();
  }, []);

  const loadAIProvidersStatus = async () => {
    try {
      const response = await apiClient.settings.getAIProvidersStatus();
      const configured = new Set<AIProvider>();
      response.providers.forEach((p) => {
        if (p.configured) {
          configured.add(p.provider as AIProvider);
        }
      });
      setConfiguredProviders(configured);

      // If at least one AI provider is configured, mark the AI step as completed
      if (configured.size > 0) {
        setCompletedSteps((prev) => new Set([...prev, 'ai']));
      }
    } catch (error) {
      console.error('Failed to load AI providers status:', error);
    }
  };

  const currentStepData = SETUP_STEPS[currentStep];
  const progress = ((currentStep + 1) / SETUP_STEPS.length) * 100;

  const canProceed = () => {
    if (currentStepData.id === 'ai') {
      // At least one AI provider must be configured
      return configuredProviders.size > 0;
    }
    return true;
  };

  const handleNext = () => {
    if (currentStep < SETUP_STEPS.length - 1) {
      // Mark current step as completed if conditions are met
      if (canProceed()) {
        setCompletedSteps((prev) => new Set([...prev, currentStepData.id]));
      }
      setCurrentStep(currentStep + 1);
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSkip = () => {
    if (!currentStepData.required) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handleComplete = () => {
    setCompletedSteps((prev) => new Set([...prev, 'complete']));
    onComplete();
  };

  const handleTestApiKey = async (provider: AIProvider) => {
    const key = aiKeys[provider];
    if (!key.trim()) {
      toast.error('Please enter an API key');
      return;
    }

    setTestingProvider(provider);
    try {
      const response = await apiClient.settings.testApiKey({
        provider,
        api_key: key,
      });

      if (response.valid) {
        setTestedProviders((prev) => ({ ...prev, [provider]: 'success' }));
        toast.success(`${AI_PROVIDERS.find(p => p.provider === provider)?.name} API key is valid!`);
      } else {
        setTestedProviders((prev) => ({ ...prev, [provider]: 'error' }));
        toast.error(response.message || 'API key validation failed');
      }
    } catch {
      setTestedProviders((prev) => ({ ...prev, [provider]: 'error' }));
      toast.error('Failed to test API key');
    } finally {
      setTestingProvider(null);
    }
  };

  const handleSaveApiKey = async (provider: AIProvider) => {
    const key = aiKeys[provider];
    if (!key.trim()) {
      toast.error('Please enter an API key');
      return;
    }

    // Map provider to API key field name
    const keyFieldMap: Record<AIProvider, string> = {
      openai: 'ai_api_key_openai',
      grok: 'ai_api_key_grok',
      anthropic: 'ai_api_key_claude',
      google: 'ai_api_key_gemini',
    };

    setSavingProvider(provider);
    try {
      await apiClient.settings.update({
        [keyFieldMap[provider]]: key,
      } as Record<string, string>);

      setConfiguredProviders((prev) => new Set([...prev, provider]));
      setCompletedSteps((prev) => new Set([...prev, 'ai']));
      toast.success(`${AI_PROVIDERS.find(p => p.provider === provider)?.name} API key saved!`);

      // Clear the input after saving
      setAiKeys((prev) => ({ ...prev, [provider]: '' }));
      setTestedProviders((prev) => ({ ...prev, [provider]: null }));
    } catch {
      toast.error('Failed to save API key');
    } finally {
      setSavingProvider(null);
    }
  };

  const renderStepIndicator = () => (
    <div className="flex items-center justify-center gap-2 mb-6">
      {SETUP_STEPS.map((step, index) => (
        <div
          key={step.id}
          className="flex items-center"
        >
          <div
            className={`flex items-center justify-center w-8 h-8 rounded-full border-2 transition-colors ${
              completedSteps.has(step.id)
                ? 'bg-green-500 border-green-500 text-white'
                : index === currentStep
                ? 'bg-primary border-primary text-primary-foreground'
                : 'border-muted-foreground/30 text-muted-foreground'
            }`}
          >
            {completedSteps.has(step.id) ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <span className="text-xs font-medium">{index + 1}</span>
            )}
          </div>
          {index < SETUP_STEPS.length - 1 && (
            <div
              className={`w-8 h-0.5 mx-1 ${
                completedSteps.has(step.id) ? 'bg-green-500' : 'bg-muted-foreground/30'
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );

  const renderWelcomeStep = () => (
    <div className="text-center space-y-6">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
        <Brain className="h-8 w-8 text-primary" />
      </div>
      <div className="space-y-2">
        <h2 className="text-2xl font-bold">Welcome to Live Object AI Classifier</h2>
        <p className="text-muted-foreground max-w-md mx-auto">
          AI-powered event detection and monitoring for your home security cameras.
          Let&apos;s get you set up in just a few steps.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4">
        <div className="p-4 rounded-lg border bg-card">
          <Brain className="h-6 w-6 text-primary mb-2" />
          <h3 className="font-medium">AI-Powered</h3>
          <p className="text-sm text-muted-foreground">Natural language descriptions of events</p>
        </div>
        <div className="p-4 rounded-lg border bg-card">
          <Video className="h-6 w-6 text-primary mb-2" />
          <h3 className="font-medium">Multi-Camera</h3>
          <p className="text-sm text-muted-foreground">RTSP, USB, and UniFi Protect support</p>
        </div>
        <div className="p-4 rounded-lg border bg-card">
          <Shield className="h-6 w-6 text-primary mb-2" />
          <h3 className="font-medium">Smart Alerts</h3>
          <p className="text-sm text-muted-foreground">Custom rules and webhook notifications</p>
        </div>
      </div>
    </div>
  );

  const renderAIStep = () => (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <h2 className="text-xl font-bold">Configure AI Provider</h2>
        <p className="text-muted-foreground">
          Add at least one AI provider API key to enable event descriptions.
          Multiple providers create automatic fallback.
        </p>
      </div>

      {configuredProviders.size > 0 && (
        <div className="p-3 rounded-lg border border-green-500/50 bg-green-500/10 flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-green-500" />
          <span className="text-sm">
            {configuredProviders.size} provider{configuredProviders.size > 1 ? 's' : ''} configured:
            {' '}
            {Array.from(configuredProviders).map(p =>
              AI_PROVIDERS.find(ap => ap.provider === p)?.name
            ).join(', ')}
          </span>
        </div>
      )}

      <div className="space-y-4">
        {AI_PROVIDERS.map((provider) => (
          <Card key={provider.provider} className={configuredProviders.has(provider.provider) ? 'border-green-500/50' : ''}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    {provider.name}
                    {configuredProviders.has(provider.provider) && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-green-500/20 text-green-500">
                        <Check className="h-3 w-3 mr-1" />
                        Configured
                      </span>
                    )}
                  </CardTitle>
                  <CardDescription>{provider.description}</CardDescription>
                </div>
                <a
                  href={provider.docsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                >
                  Get API Key
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </CardHeader>
            {!configuredProviders.has(provider.provider) && (
              <CardContent className="pb-4">
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Input
                      type={showKeys[provider.provider] ? 'text' : 'password'}
                      placeholder={provider.placeholder}
                      value={aiKeys[provider.provider]}
                      onChange={(e) =>
                        setAiKeys((prev) => ({ ...prev, [provider.provider]: e.target.value }))
                      }
                      className="pr-10"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7 p-0"
                      onClick={() =>
                        setShowKeys((prev) => ({ ...prev, [provider.provider]: !prev[provider.provider] }))
                      }
                    >
                      {showKeys[provider.provider] ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => handleTestApiKey(provider.provider)}
                    disabled={!aiKeys[provider.provider] || testingProvider === provider.provider}
                  >
                    {testingProvider === provider.provider ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : testedProviders[provider.provider] === 'success' ? (
                      <Check className="h-4 w-4 text-green-500" />
                    ) : testedProviders[provider.provider] === 'error' ? (
                      <X className="h-4 w-4 text-red-500" />
                    ) : (
                      'Test'
                    )}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => handleSaveApiKey(provider.provider)}
                    disabled={!aiKeys[provider.provider] || savingProvider === provider.provider}
                  >
                    {savingProvider === provider.provider ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      'Save'
                    )}
                  </Button>
                </div>
              </CardContent>
            )}
          </Card>
        ))}
      </div>

      {configuredProviders.size === 0 && (
        <div className="p-3 rounded-lg border border-yellow-500/50 bg-yellow-500/10 flex items-start gap-2">
          <AlertTriangle className="h-5 w-5 text-yellow-500 shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium">At least one AI provider is required</p>
            <p className="text-muted-foreground">
              Enter and save an API key above to continue. We recommend starting with OpenAI.
            </p>
          </div>
        </div>
      )}
    </div>
  );

  const renderCameraStep = () => (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <h2 className="text-xl font-bold">Add Camera Source (Optional)</h2>
        <p className="text-muted-foreground">
          You can add cameras now or later from the Cameras page.
        </p>
      </div>

      <div className="grid gap-4">
        <Card className="cursor-pointer hover:border-primary transition-colors">
          <CardHeader>
            <CardTitle className="text-base">RTSP Camera</CardTitle>
            <CardDescription>Connect to an IP camera using RTSP protocol</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => {
                window.location.href = '/cameras?add=rtsp';
              }}
            >
              Add RTSP Camera
            </Button>
          </CardContent>
        </Card>

        <Card className="cursor-pointer hover:border-primary transition-colors">
          <CardHeader>
            <CardTitle className="text-base">USB Webcam</CardTitle>
            <CardDescription>Use a USB webcam connected to this computer</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => {
                window.location.href = '/cameras?add=usb';
              }}
            >
              Add USB Camera
            </Button>
          </CardContent>
        </Card>
      </div>

      <p className="text-sm text-muted-foreground text-center">
        For UniFi Protect cameras, continue to the next step to connect your controller.
      </p>
    </div>
  );

  const renderProtectStep = () => (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <h2 className="text-xl font-bold">UniFi Protect Integration (Optional)</h2>
        <p className="text-muted-foreground">
          Connect your UniFi Protect controller for native camera integration.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Shield className="h-5 w-5 text-cyan-500" />
            UniFi Protect Controller
          </CardTitle>
          <CardDescription>
            Auto-discover cameras, receive real-time events, and process doorbell notifications
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="p-4 rounded-lg bg-muted/50 space-y-2 text-sm">
              <p><strong>Benefits:</strong></p>
              <ul className="list-disc list-inside space-y-1 text-muted-foreground">
                <li>Automatic camera discovery</li>
                <li>Real-time WebSocket events</li>
                <li>Smart detection types (Person, Vehicle, Package, Animal)</li>
                <li>Doorbell ring notifications</li>
                <li>Multi-camera event correlation</li>
              </ul>
            </div>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => {
                window.location.href = '/settings?tab=protect';
              }}
            >
              Configure UniFi Protect
            </Button>
          </div>
        </CardContent>
      </Card>

      <p className="text-sm text-muted-foreground text-center">
        You can configure this later from Settings &gt; UniFi Protect.
      </p>
    </div>
  );

  const renderCompleteStep = () => (
    <div className="text-center space-y-6">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-500/20 mb-4">
        <CheckCircle2 className="h-8 w-8 text-green-500" />
      </div>
      <div className="space-y-2">
        <h2 className="text-2xl font-bold">Setup Complete!</h2>
        <p className="text-muted-foreground max-w-md mx-auto">
          Your Live Object AI Classifier is ready to use. You can now start monitoring your cameras.
        </p>
      </div>

      <div className="space-y-3 pt-4">
        <div className="p-4 rounded-lg border bg-card text-left">
          <h3 className="font-medium mb-2">What&apos;s Next?</h3>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li className="flex items-center gap-2">
              <Circle className="h-2 w-2 fill-current" />
              Add cameras from the Cameras page
            </li>
            <li className="flex items-center gap-2">
              <Circle className="h-2 w-2 fill-current" />
              Configure alert rules for notifications
            </li>
            <li className="flex items-center gap-2">
              <Circle className="h-2 w-2 fill-current" />
              View detected events on the Dashboard
            </li>
            <li className="flex items-center gap-2">
              <Circle className="h-2 w-2 fill-current" />
              Customize settings as needed
            </li>
          </ul>
        </div>
      </div>
    </div>
  );

  const renderStepContent = () => {
    switch (currentStepData.id) {
      case 'welcome':
        return renderWelcomeStep();
      case 'ai':
        return renderAIStep();
      case 'camera':
        return renderCameraStep();
      case 'protect':
        return renderProtectStep();
      case 'complete':
        return renderCompleteStep();
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-gradient-to-b from-background to-muted/20">
      <Card className="w-full max-w-2xl">
        <CardHeader className="text-center pb-2">
          <Progress value={progress} className="h-1 mb-4" />
          {renderStepIndicator()}
          <CardTitle className="flex items-center justify-center gap-2">
            {currentStepData.icon}
            {currentStepData.title}
          </CardTitle>
          <CardDescription>{currentStepData.description}</CardDescription>
        </CardHeader>
        <CardContent className="pt-4">
          {renderStepContent()}
        </CardContent>
        <CardFooter className="flex justify-between pt-4 border-t">
          <Button
            type="button"
            variant="ghost"
            onClick={handleBack}
            disabled={currentStep === 0}
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <div className="flex gap-2">
            {!currentStepData.required && currentStep < SETUP_STEPS.length - 1 && (
              <Button
                type="button"
                variant="ghost"
                onClick={handleSkip}
              >
                Skip
              </Button>
            )}
            {currentStep < SETUP_STEPS.length - 1 ? (
              <Button
                type="button"
                onClick={handleNext}
                disabled={!canProceed()}
              >
                Next
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            ) : (
              <Button
                type="button"
                onClick={handleComplete}
              >
                Go to Dashboard
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            )}
          </div>
        </CardFooter>
      </Card>
    </div>
  );
}
