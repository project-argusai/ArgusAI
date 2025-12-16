/**
 * AI Providers Configuration Component
 * Story P2-5.2: Build Grok Provider Configuration UI
 *
 * Displays a list of AI providers with:
 * - Status indicators (Configured/Not configured)
 * - Setup/Edit buttons
 * - Configuration forms for API keys
 * - Drag-to-reorder for fallback priority (AC6)
 */

'use client';

import { useState, useEffect } from 'react';
import {
  Brain,
  CheckCircle2,
  XCircle,
  Loader2,
  Eye,
  EyeOff,
  Sparkles,
  GripVertical,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

import { apiClient } from '@/lib/api-client';
import type { AIProvider } from '@/types/settings';

// Provider configuration data
const PROVIDER_DATA: Record<
  AIProvider,
  {
    name: string;
    description: string;
    model: string;
    icon: React.ReactNode;
  }
> = {
  openai: {
    name: 'OpenAI',
    description: 'GPT-4o mini - Fast and capable vision model',
    model: 'gpt-4o-mini',
    icon: <Brain className="h-5 w-5" />,
  },
  grok: {
    name: 'xAI Grok',
    description: "Grok Vision - xAI's vision-capable model",
    model: 'grok-2-vision-1212',
    icon: <Sparkles className="h-5 w-5" />,
  },
  anthropic: {
    name: 'Anthropic Claude',
    description: 'Claude 3 Haiku - Efficient and accurate',
    model: 'claude-3-haiku',
    icon: <Brain className="h-5 w-5" />,
  },
  google: {
    name: 'Google Gemini',
    description: "Gemini Flash - Google's fast vision model",
    model: 'gemini-flash',
    icon: <Brain className="h-5 w-5" />,
  },
};

// Default provider order
const DEFAULT_PROVIDER_ORDER: AIProvider[] = ['openai', 'grok', 'anthropic', 'google'];

interface SortableProviderRowProps {
  providerId: AIProvider;
  isConfigured: boolean;
  onSetup: (id: AIProvider) => void;
  onEdit: (id: AIProvider) => void;
  onRemove: (id: AIProvider) => void;
}

function SortableProviderRow({
  providerId,
  isConfigured,
  onSetup,
  onEdit,
  onRemove,
}: SortableProviderRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: providerId,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const provider = PROVIDER_DATA[providerId];

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center justify-between p-4 border rounded-lg ${
        isDragging ? 'bg-muted' : ''
      }`}
    >
      <div className="flex items-center gap-4">
        {/* Drag handle */}
        <button
          {...attributes}
          {...listeners}
          className="p-1 hover:bg-muted rounded cursor-grab active:cursor-grabbing focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
          aria-label="Drag to reorder"
        >
          <GripVertical className="h-5 w-5 text-muted-foreground" />
        </button>
        <div className="p-2 bg-muted rounded-md">{provider.icon}</div>
        <div>
          <div className="font-medium flex items-center gap-2">
            {provider.name}
            {isConfigured ? (
              <span className="text-xs text-green-600 flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" />
                Configured
              </span>
            ) : (
              <span className="text-xs text-muted-foreground">Not configured</span>
            )}
          </div>
          <div className="text-sm text-muted-foreground">{provider.description}</div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {isConfigured ? (
          <>
            <Button variant="outline" size="sm" onClick={() => onEdit(providerId)}>
              Edit
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:text-destructive"
              onClick={() => onRemove(providerId)}
            >
              Remove
            </Button>
          </>
        ) : (
          <Button variant="default" size="sm" onClick={() => onSetup(providerId)}>
            Setup
          </Button>
        )}
      </div>
    </div>
  );
}

interface AIProvidersProps {
  configuredProviders: Set<AIProvider>;
  providerOrder?: AIProvider[];
  onProviderConfigured: (provider: AIProvider) => void;
  onProviderRemoved: (provider: AIProvider) => void;
  onProviderOrderChanged?: (order: AIProvider[]) => void;
}

export function AIProviders({
  configuredProviders,
  providerOrder: initialOrder,
  onProviderConfigured,
  onProviderRemoved,
  onProviderOrderChanged,
}: AIProvidersProps) {
  const [selectedProvider, setSelectedProvider] = useState<AIProvider | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isRemoveDialogOpen, setIsRemoveDialogOpen] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [isTestingKey, setIsTestingKey] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ valid: boolean; error?: string } | null>(null);
  const [providerOrder, setProviderOrder] = useState<AIProvider[]>(
    initialOrder || DEFAULT_PROVIDER_ORDER
  );

  // Update order when prop changes
  useEffect(() => {
    if (initialOrder) {
      setProviderOrder(initialOrder);
    }
  }, [initialOrder]);

  // Drag and drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      const oldIndex = providerOrder.indexOf(active.id as AIProvider);
      const newIndex = providerOrder.indexOf(over.id as AIProvider);
      const newOrder = arrayMove(providerOrder, oldIndex, newIndex);

      setProviderOrder(newOrder);

      // Save the new order to the backend
      try {
        await apiClient.settings.update({
          ai_provider_order: JSON.stringify(newOrder),
        } as Record<string, string>);
        toast.success('Provider order updated');
        onProviderOrderChanged?.(newOrder);
      } catch (error) {
        console.error('Failed to save provider order:', error);
        toast.error('Failed to save provider order');
        // Revert on error
        setProviderOrder(providerOrder);
      }
    }
  };

  const handleSetup = (providerId: AIProvider) => {
    setSelectedProvider(providerId);
    setApiKey('');
    setTestResult(null);
    setShowApiKey(false);
    setIsDialogOpen(true);
  };

  const handleEdit = (providerId: AIProvider) => {
    setSelectedProvider(providerId);
    setApiKey(''); // Don't show existing key, user must re-enter
    setTestResult(null);
    setShowApiKey(false);
    setIsDialogOpen(true);
  };

  const handleRemoveClick = (providerId: AIProvider) => {
    setSelectedProvider(providerId);
    setIsRemoveDialogOpen(true);
  };

  const handleTestKey = async () => {
    if (!selectedProvider || !apiKey) return;

    setIsTestingKey(true);
    setTestResult(null);

    try {
      const result = await apiClient.settings.testApiKey({
        provider: selectedProvider,
        api_key: apiKey,
      });

      setTestResult({ valid: result.valid, error: result.valid ? undefined : result.message });

      if (result.valid) {
        toast.success(result.message || 'API key validated successfully');
      } else {
        toast.error(result.message || 'API key validation failed');
      }
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Connection failed';
      setTestResult({ valid: false, error: errorMessage });
      toast.error(errorMessage);
    } finally {
      setIsTestingKey(false);
    }
  };

  const handleSave = async () => {
    if (!selectedProvider || !apiKey) return;

    setIsSaving(true);

    try {
      // Map provider to API key field name
      const keyFieldMap: Record<AIProvider, string> = {
        openai: 'ai_api_key_openai',
        grok: 'ai_api_key_grok',
        anthropic: 'ai_api_key_claude',
        google: 'ai_api_key_gemini',
      };

      const keyField = keyFieldMap[selectedProvider];

      // Save the API key using the settings update endpoint
      await apiClient.settings.update({
        [keyField]: apiKey,
      } as Record<string, string>);

      toast.success(`${getProviderName(selectedProvider)} configured successfully`);
      onProviderConfigured(selectedProvider);
      setIsDialogOpen(false);
      setApiKey('');
      setTestResult(null);
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to save API key';
      toast.error(errorMessage);
    } finally {
      setIsSaving(false);
    }
  };

  const handleRemove = async () => {
    if (!selectedProvider) return;

    try {
      // Map provider to API key field name
      const keyFieldMap: Record<AIProvider, string> = {
        openai: 'ai_api_key_openai',
        grok: 'ai_api_key_grok',
        anthropic: 'ai_api_key_claude',
        google: 'ai_api_key_gemini',
      };

      const keyField = keyFieldMap[selectedProvider];

      // Remove by setting to empty string
      await apiClient.settings.update({
        [keyField]: '',
      } as Record<string, string>);

      toast.success(`${getProviderName(selectedProvider)} removed`);
      onProviderRemoved(selectedProvider);
      setIsRemoveDialogOpen(false);
    } catch (error: unknown) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to remove provider';
      toast.error(errorMessage);
    }
  };

  const getProviderName = (providerId: AIProvider): string => {
    return PROVIDER_DATA[providerId]?.name || providerId;
  };

  const selectedProviderData = selectedProvider ? PROVIDER_DATA[selectedProvider] : null;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>AI Providers</CardTitle>
          <CardDescription>
            Configure API keys for AI vision providers. Drag to reorder fallback priority.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={providerOrder} strategy={verticalListSortingStrategy}>
              {providerOrder.map((providerId) => (
                <SortableProviderRow
                  key={providerId}
                  providerId={providerId}
                  isConfigured={configuredProviders.has(providerId)}
                  onSetup={handleSetup}
                  onEdit={handleEdit}
                  onRemove={handleRemoveClick}
                />
              ))}
            </SortableContext>
          </DndContext>
        </CardContent>
      </Card>

      {/* Configuration Dialog */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {configuredProviders.has(selectedProvider!) ? 'Edit' : 'Setup'}{' '}
              {selectedProviderData?.name}
            </DialogTitle>
            <DialogDescription>
              Enter your API key to enable {selectedProviderData?.name} for event descriptions.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="provider-api-key">API Key</Label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    id="provider-api-key"
                    type={showApiKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Enter API key"
                  />
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => setShowApiKey(!showApiKey)}
                >
                  {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
              {testResult && !testResult.valid && (
                <p className="text-sm text-destructive">{testResult.error}</p>
              )}
            </div>
            <Button
              type="button"
              variant="secondary"
              onClick={handleTestKey}
              disabled={isTestingKey || !apiKey}
              className="w-full"
            >
              {isTestingKey && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {testResult?.valid && <CheckCircle2 className="h-4 w-4 mr-2 text-green-600" />}
              {testResult?.valid === false && <XCircle className="h-4 w-4 mr-2 text-destructive" />}
              Test API Key
            </Button>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={!apiKey || isSaving}>
              {isSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Remove Confirmation Dialog */}
      <AlertDialog open={isRemoveDialogOpen} onOpenChange={setIsRemoveDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove {selectedProviderData?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              This will remove the API key for {selectedProviderData?.name}. The provider will no
              longer be available for generating event descriptions.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRemove}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
