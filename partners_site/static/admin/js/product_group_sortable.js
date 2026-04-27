(function () {
  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : '';
  }

  function getRowId(row) {
    const checkbox = row.querySelector('input.action-select[name="_selected_action"]');
    return checkbox ? checkbox.value : null;
  }

  function getRows(tbody) {
    return Array.from(tbody.querySelectorAll('tr')).filter(row => getRowId(row));
  }

  function getDropTarget(tbody, y) {
    const rows = getRows(tbody).filter(row => !row.classList.contains('is-dragging'));

    return rows.reduce((closest, row) => {
      const rect = row.getBoundingClientRect();
      const offset = y - rect.top - rect.height / 2;

      if (offset < 0 && offset > closest.offset) {
        return { offset, row };
      }

      return closest;
    }, { offset: Number.NEGATIVE_INFINITY, row: null }).row;
  }

  function updateSortInputs(tbody, positions) {
    getRows(tbody).forEach(row => {
      const rowId = getRowId(row);
      const sortInput = row.querySelector('input[name$="-sort_order"]');
      if (rowId && sortInput && positions[rowId] != null) {
        sortInput.value = positions[rowId];
      }
    });
  }

  async function saveOrder(tbody) {
    const rows = getRows(tbody);
    const orderedIds = rows.map(row => getRowId(row)).filter(Boolean);
    if (!orderedIds.length) return;

    rows.forEach(row => row.classList.add('is-saving'));

    try {
      const response = await fetch(`${window.location.pathname.replace(/\/$/, '')}/reorder/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ ordered_ids: orderedIds }),
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok || !data.success) {
        throw new Error(data.error || 'Не удалось сохранить порядок');
      }

      updateSortInputs(tbody, data.positions || {});
    } catch (error) {
      window.alert(error.message || 'Не удалось сохранить порядок');
      window.location.reload();
    } finally {
      rows.forEach(row => row.classList.remove('is-saving'));
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!document.body.classList.contains('model-productgroup')) return;
    if (!document.body.classList.contains('change-list')) return;

    const tbody = document.querySelector('#result_list tbody');
    if (!tbody) return;

    let draggedRow = null;
    let orderChanged = false;

    getRows(tbody).forEach(row => {
      row.draggable = true;
      row.classList.add('productgroup-sortable-row');

      row.addEventListener('dragstart', event => {
        draggedRow = row;
        orderChanged = false;
        row.classList.add('is-dragging');
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', getRowId(row) || '');
      });

      row.addEventListener('dragend', () => {
        row.classList.remove('is-dragging');
        draggedRow = null;

        if (orderChanged) {
          saveOrder(tbody);
        }
      });
    });

    tbody.addEventListener('dragover', event => {
      if (!draggedRow) return;
      event.preventDefault();

      const target = getDropTarget(tbody, event.clientY);
      if (target == null) {
        tbody.appendChild(draggedRow);
      } else {
        tbody.insertBefore(draggedRow, target);
      }
      orderChanged = true;
    });
  });
}());
