/**
 * virtual-grid/virtual-grid-data.ts
 *
 * In-memory store for ResultRecords.
 * Holds data independently of the DOM, serving as the data source for virtual scrolling.
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ResultRecord = Record<string, any>;

/**
 * In-memory store for search result data.
 */
export class VirtualGridDataStore {
  private _items: ResultRecord[] = [];

  /** Get all items */
  get items(): readonly ResultRecord[] {
    return this._items;
  }

  /** Total item count */
  get length(): number {
    return this._items.length;
  }

  /** Set all items (for displayResults) */
  setAll(items: ResultRecord[]): void {
    this._items = [...items];
  }

  /** Append items (for appendResults) */
  append(items: ResultRecord[]): void {
    this._items.push(...items);
  }

  /** Clear all */
  clear(): void {
    this._items = [];
  }

  /** Get a range (for virtual scroll rendering) */
  slice(start: number, end: number): ResultRecord[] {
    return this._items.slice(start, end);
  }

  /** Find index by ID */
  indexById(id: number): number {
    return this._items.findIndex((item) => item.id === id);
  }

  /** Get item by index */
  getAt(index: number): ResultRecord | undefined {
    return this._items[index];
  }

  /** Return all IDs as an array */
  getAllIds(): number[] {
    return this._items
      .map((item) => item.id as number)
      .filter((id) => typeof id === 'number');
  }
}
