export enum DocumentStatusesEnum {
  progress = 'progress',
  upgrading = 'upgrading',
  done = 'done',
}

export interface Document {
  file_uuid: string,
  group_uuid: string,
  filename: string,
  status: DocumentStatusesEnum,
}

export interface FileContent {
  file_uuid: string;
  json: {
    scan: {
      dimensions: {
        width: number;
        height: number;
      };
    };
    regions: Array<{
      id: string;
      type?: string;
      index?: number;
      concatenated_text: string;
      coordinates?: {
        bounding_box: {
          top_left: { x: number; y: number };
          top_right: { x: number; y: number };
          bottom_left: { x: number; y: number };
          bottom_right: { x: number; y: number };
        };
      };
      lines: Array<{
        id: string;
        text: string;
        coordinates?: {
          original: string;
        };
      }>;
      corrected_text?: string;
      named_entities?: Array<{
        entity_type: string;
        entity_value: string;
        details: string;
      }>;
      confidence?: number;
    }>;
  };
}
