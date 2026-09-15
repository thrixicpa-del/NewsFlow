import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "../components/button";
import { ErrorState } from "../components/states";

type WorkspaceErrorBoundaryProps = {
  workspace: string;
  children: ReactNode;
  onRetry?: () => void;
};

type WorkspaceErrorBoundaryState = { failed: boolean; correlationId?: string };

export class WorkspaceErrorBoundary extends Component<WorkspaceErrorBoundaryProps, WorkspaceErrorBoundaryState> {
  state: WorkspaceErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): WorkspaceErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // Error recovery is renderer-local. Runtime state stays owned by the caller.
    this.setState({ correlationId: `${this.props.workspace}-${Date.now().toString(36)}` });
  }

  private retry = (): void => {
    this.props.onRetry?.();
    this.setState({ failed: false, correlationId: undefined });
  };

  render(): ReactNode {
    if (this.state.failed) {
      return <div role="alert"><ErrorState
        title={`Рабочая область ${this.props.workspace} временно недоступна`}
        description="Данные и задачи не изменены. Повторная загрузка восстановит только интерфейс этой области."
        action={<Button onClick={this.retry}>Повторить загрузку области</Button>}
      /><p className="nf-error-correlation">Код диагностики: {this.state.correlationId || `${this.props.workspace}-initializing`}</p></div>;
    }
    return this.props.children;
  }
}
