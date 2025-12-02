<?php
/*
Plugin Name: Export stats to google spreadsheets
Description: Exports stats to google spreadsheets
Version: 1.0
Author: Denis Bogdanov
License: GPL2
*/

class Export_stats {
    // Constructor
    public function __construct() {
        //add_action('wp_enqueue_scripts', array($this, 'enqueue_scripts'));
        register_activation_hook(__FILE__, array($this, 'activate'));
        register_deactivation_hook(__FILE__, array($this, 'deactivate'));


        add_action('admin_menu', array($this, 'add_admin_menu'));
        //add_action('export_stats_hourly_event', array($this, 'hourly_cron_job'));
        add_action('export_stats_daily_event', array($this, 'daily_cron_job'));
        add_action('export_openai_daily_event', array($this, 'export_openai_stats_to_sheets'));

        add_action('admin_init', array($this, 'maybe_export_refunds_csv'));


        add_action('rsc_cron_task', [$this, 'run_scheduled_customer_checks']);
        add_action('admin_init', [$this, 'ensure_cron_task_scheduled']);
    }

    function ensure_cron_task_scheduled() {
        //update_option('status_check_current_date', '2025-04-30');
        //update_option('status_check_last_offset', 0);
        if (!wp_next_scheduled('rsc_cron_task')) {
            //wp_schedule_event(time(), 'three_minutes', 'rsc_cron_task');
        }
    }



    public function run_scheduled_customer_checks() {
        $date = get_option('status_check_current_date', date('Y-m-d'));

        $offset = (int) get_option('status_check_last_offset', 0);
        $batch_size = 300;

        $this->log_message("Running scheduled customer status checks for date: {$date}");
        $this->log_message("Current offset: {$offset}, batch size: {$batch_size}");

        // Step 1: Load raw order IDs for this batch
        $raw_order_ids = wc_get_orders([
            'limit'        => $batch_size,
            'offset'       => $offset,
            'type'         => 'shop_order',
            'status'       => ['wc-completed', 'wc-processing', 'wc-on-hold', 'wc-refunded'],
            'date_created' => "{$date} 00:00:00...{$date} 23:59:59",
            'return'       => 'ids',
        ]);

        // Step 2: Filter by time offset (your custom logic)
        $order_ids = $this->filter_orders_with_time_offset($raw_order_ids, $date);

        if (empty($order_ids)) {
            // Done with current day
            $new_date = date('Y-m-d', strtotime($date . ' -1 day'));
            update_option('status_check_current_date', $new_date);
            update_option('status_check_last_offset', 0);
            $this->log_message("✅ Finished processing {$date}, moving to {$new_date}");
            $this->run_scheduled_customer_checks();
            return;
        }

        $changed = 0;
        foreach ($order_ids as $order_id) {
            $order = wc_get_order($order_id);
            if (!$order) continue;

            $before = $order->get_meta('new_or_returning');
            define_new_order_customer_status($order_id, $order);
            $after = $order->get_meta('new_or_returning');

            if ($before !== $after) {
                $changed++;
            }
        }

        $new_offset = $offset + $batch_size;
        update_option('status_check_last_offset', $new_offset);

        $this->log_message("📦 Processed batch from offset {$offset} — {$changed} updated");
    }




    public function maybe_export_refunds_csv() {
        if (
            is_admin() &&
            isset($_GET['export_refunds']) &&
            $_GET['export_refunds'] === '1' &&
            isset($_GET['date_from']) &&
            isset($_GET['date_to']) &&
            current_user_can('manage_options')
        ) {
            $date_from = sanitize_text_field($_GET['date_from']);
            $date_to = sanitize_text_field($_GET['date_to']);

            // Early exit if headers were already sent
            if (headers_sent()) {
                wp_die('Cannot export CSV: headers already sent.');
            }

            $this->export_refunds_csv($date_from, $date_to);
        }
    }


    /* ==================== REFUND CSV EXPORT ==================== */
    private function export_refunds_csv($date_from, $date_to) {
        $wc_args = array(
            'limit'        => -1,
            'type'         => 'shop_order_refund',
            'return'       => 'ids',
            'date_created' => $date_from . '...' . $date_to,
        );
        $refund_ids = wc_get_orders($wc_args);

        if (empty($refund_ids)) {
            $this->generate_csv_download([], $date_from, $date_to);
            return;
        }

        $filtered_refund_ids = $this->filter_orders_with_time_offset_range($refund_ids, $date_from, $date_to, 'shop_order_refund');

        $csv_data = [];
        $csv_data[] = array(
            'Refund ID',
            'Parent Order ID',
            'Order Created Date',
            'Order Total',
            'Order Tax',
            'Shipping Country',
            'Shipping State',
            'Shipping City',
            'Shipping Postcode',
            'Shipping Address 1',
            'Shipping Address 2',
            'Refund Created Date',
            'Refund Total',
            'Refunded Tax',
            'Refunded Shipping',
            'Customer Email',
            'Customer Name',
            'Reason'
        );

        foreach ($filtered_refund_ids as $refund_id) {
            $refund = wc_get_order($refund_id);
            if (!$refund) {
                continue;
            }

            $refund_data = $refund->get_data();
            $parent_order_id = $refund->get_parent_id();
            $parent_order    = wc_get_order($parent_order_id);

            $order_created_date = $parent_order && $parent_order->get_date_created()
                ? $parent_order->get_date_created()->date_i18n('Y-m-d H:i:s')
                : '';
            $order_total = $parent_order ? $parent_order->get_total() : '';
            $order_tax   = $parent_order ? $parent_order->get_total_tax() : '';

            $shipping_country    = $parent_order ? $parent_order->get_shipping_country() : '';
            $shipping_state      = $parent_order ? $parent_order->get_shipping_state() : '';
            /*
            if (!in_array($shipping_state, ['CA', 'MO', 'PA', 'WA'], true)) {
                continue;
            }
            */

            $shipping_city       = $parent_order ? $parent_order->get_shipping_city() : '';
            $shipping_postcode   = $parent_order ? $parent_order->get_shipping_postcode() : '';
            $shipping_address_1  = $parent_order ? $parent_order->get_shipping_address_1() : '';
            $shipping_address_2  = $parent_order ? $parent_order->get_shipping_address_2() : '';

            $created_date  = $refund->get_date_created() ? $refund->get_date_created()->date_i18n('Y-m-d H:i:s') : '';
            $refunded_total = abs($refund->get_amount());
            $refunded_shipping = 0;
            $refunded_tax = 0;

            foreach ($refund->get_items('shipping') as $item) {
                $refunded_shipping += abs($item->get_total());
            }
            foreach ($refund->get_items('tax') as $tax_item) {
                $refunded_tax += abs($tax_item->get_tax_total());
            }

            $order_currency = $refund->get_currency();
            $exchange_rate = $this->get_rate($order_currency, $this->get_cur_rates());
            if ($exchange_rate && $exchange_rate > 0) {
                $refunded_total    = $refunded_total / $exchange_rate;
                $refunded_tax      = $refunded_tax / $exchange_rate;
                $refunded_shipping = $refunded_shipping / $exchange_rate;
            }

            $customer_email = $parent_order ? $parent_order->get_billing_email() : '';
            $customer_name  = $parent_order
                ? trim($parent_order->get_billing_first_name() . ' ' . $parent_order->get_billing_last_name())
                : '';
            $reason = $refund->get_reason();

            $csv_data[] = array(
                $refund_id,
                $parent_order_id,
                $order_created_date,
                $order_total,
                $order_tax,
                $shipping_country,
                $shipping_state,
                $shipping_city,
                $shipping_postcode,
                $shipping_address_1,
                $shipping_address_2,
                $created_date,
                $refunded_total,
                $refunded_tax,
                $refunded_shipping,
                $customer_email,
                $customer_name,
                $reason
            );
        }

        $this->generate_csv_download($csv_data, $date_from, $date_to);
    }



    /**
     * Creates and sends CSV to user browser for download
     */
    private function generate_csv_download($csv_rows, $date_from, $date_to) {
        $filename = "refunds-{$date_from}-to-{$date_to}.csv";

        header('Content-Type: text/csv; charset=utf-8');
        header('Content-Disposition: attachment; filename="' . $filename . '"');

        $output = fopen('php://output', 'w');
        foreach ($csv_rows as $row) {
            fputcsv($output, $row);
        }
        fclose($output);

        // Prevent any extra output
        exit;
    }

    /**
     * The original filter_orders_with_time_offset() was for a single date.
     * Below is a variation that checks whether an order date (with offset) is between
     * a given date range [Y-m-d ... Y-m-d].
     */
    private function filter_orders_with_time_offset_range($order_ids, $date_from, $date_to, $post_type = "shop_order") {
        $time_zone_offset_seconds = 4 * 3600;
        $result = [];

        // Convert the raw date strings to timestamps (start of day for from, end of day for to)
        // so we can compare with the adjusted order timestamps
        $start_ts = strtotime($date_from . ' 00:00:00');
        $end_ts   = strtotime($date_to   . ' 23:59:59');

        global $wpdb;
        foreach ($order_ids as $order_id) {
            $order_date_gmt = $this->get_order_date_gmt($order_id, $post_type);
            if (!$order_date_gmt) {
                continue;
            }
            // Convert to timestamp, then apply offset
            $order_ts = strtotime($order_date_gmt) - $time_zone_offset_seconds;
            // Keep this order if within date range
            if ($order_ts >= $start_ts && $order_ts <= $end_ts) {
                $result[] = $order_id;
            }
        }
        return $result;
    }

    public function hourly_cron_job() {
        $current_date = date('Y-m-d');
        $this->show_stats($current_date);
    }

    public function daily_cron_job() {
        $yesterday = date('Y-m-d', strtotime('-1 day'));
        $this->show_stats($yesterday);
    }

    public function add_admin_menu() {
        add_management_page(
            'Export Stats To Google Sheets', // Page title
            'Export Stats To Google Sheets', // Menu title
            'manage_options', // Capability
            'export-stats-plugin', // Menu slug
            array($this, 'create_admin_page') // Function
        );
    }

    public function create_admin_page() {
?>
        <div class="wrap">
            <h1>Stats for a Specific Date</h1>
            <form method="post">
                <label for="stats-date">Select Date:</label>
                <input type="date" id="stats-date" name="stats_date" required value="<?php echo isset($_POST['stats_date']) ? esc_attr($_POST['stats_date']) : ''; ?>">
                <input type="submit" value="Show Stats">
            </form>

            <hr />

            <h1>Export Refunds to CSV</h1>
            <form method="get">
                <!-- Preserve the 'page' GET param for WordPress admin -->
                <input type="hidden" name="page" value="export-stats-plugin" />
                <input type="hidden" name="export_refunds" value="1" />

                <label for="date_from">Date From:</label>
                <input type="date" id="date_from" name="date_from" required value="<?php echo isset($_GET['date_from']) ? esc_attr($_GET['date_from']) : ''; ?>">

                <label for="date_to">Date To:</label>
                <input type="date" id="date_to" name="date_to" required value="<?php echo isset($_GET['date_to']) ? esc_attr($_GET['date_to']) : ''; ?>">

                <input type="submit" value="Export Refunds">
            </form>


            <hr />

            <h1>Process Inactive Users</h1>
            <form method="post">
                <input type="hidden" name="process_inactive_users" value="1" />
                <input type="submit" class="button button-primary" value="Fetch Inactive Users">
            </form>


            <hr />
            <h1>Check New vs Returning Customers</h1>
            <form method="post">
                <label for="customer_check_date">Select Date:</label>
                <input type="date" id="customer_check_date" name="customer_check_date" required value="<?php echo esc_attr($_POST['customer_check_date'] ?? ''); ?>">
                <input type="submit" name="run_customer_check" class="button button-primary" value="Run Check">
            </form>


            <h1>Check New vs Returning by Order IDs</h1>
            <form method="post">
                <label for="custom_order_ids">Enter Order IDs (comma-separated):</label><br>
                <textarea name="custom_order_ids" id="custom_order_ids" rows="4" cols="60" required><?php echo esc_textarea($_POST['custom_order_ids'] ?? ''); ?></textarea><br><br>
                <input type="submit" name="run_custom_check" class="button button-primary" value="Run Check">
            </form>


            <hr />
            <h1>Gift Layout Orders Report</h1>
            <form method="post">
                <label for="gift_date_from">Date From:</label>
                <input type="date" id="gift_date_from" name="gift_date_from" required value="<?php echo esc_attr($_POST['gift_date_from'] ?? ''); ?>">

                <label for="gift_date_to">Date To:</label>
                <input type="date" id="gift_date_to" name="gift_date_to" required value="<?php echo esc_attr($_POST['gift_date_to'] ?? ''); ?>">

                <input type="submit" name="run_gift_layout_report" class="button button-primary" value="Run Report">
            </form>
        </div>
<?php
        // 1) Show stats if form submitted
        if (isset($_POST['stats_date']) && !empty($_POST['stats_date'])) {
            $this->show_stats(sanitize_text_field($_POST['stats_date']));
        }


        if (isset($_POST['process_inactive_users']) && $_POST['process_inactive_users'] == '1') {
            $this->process_inactive_users();
        }


        if (isset($_POST['run_customer_check']) && !empty($_POST['customer_check_date'])) {
            $this->run_customer_status_check(sanitize_text_field($_POST['customer_check_date']));
        }


        if (isset($_POST['run_custom_check']) && !empty($_POST['custom_order_ids'])) {
            $this->run_check_by_order_ids(sanitize_text_field($_POST['custom_order_ids']));
        }
    }


    public function run_check_by_order_ids($ids_csv) {
        echo "<h2>Customer Status by Order IDs</h2>";

        $ids = array_filter(array_map('intval', explode(',', $ids_csv)));

        if (empty($ids)) {
            echo "<p>No valid order IDs provided.</p>";
            return;
        }

        echo "<table style='border-collapse: collapse; margin-top: 10px;'>";
        echo "<tr><th style='border: 1px solid #ccc; padding: 6px;'>Order ID</th><th style='border: 1px solid #ccc; padding: 6px;'>Customer Status</th></tr>";

        foreach ($ids as $order_id) {
            $order = wc_get_order($order_id);
            if (!$order) continue;

            define_new_order_customer_status($order_id, $order);
            $status = $order->get_meta('new_or_returning') ?: '';

            echo "<tr><td style='border: 1px solid #ccc; padding: 6px;'>{$order_id}</td><td style='border: 1px solid #ccc; padding: 6px;'>{$status}</td></tr>";
        }

        echo "</table>";
    }


    public function run_customer_status_check($date) {
        $function_start = microtime(true); // 🟢 Start timing the whole function

        echo "<h2>Customer Status for Orders on {$date} started</h2>";
        $this->log_message("🟢 =================== Starting customer status check for date: {$date} =================");
        $orders = wc_get_orders([
            'limit'        => -1,
            'type'         => 'shop_order',
            'status'       => ['wc-completed', 'wc-processing', 'wc-on-hold', 'wc-refunded'],
            'date_created' => "{$date} 00:00:00...{$date} 23:59:59",
            'return'       => 'ids',
        ]);

        $orders = $this->filter_orders_with_time_offset($orders, $date);

        if (empty($orders)) {
            echo "<p>No orders found for selected date.</p>";
            return;
        }

        $processed = 0;
        $changed   = 0;

        foreach ($orders as $order_id) {
            $order_start = microtime(true); // ⏱️ Per-order start

            $order = wc_get_order($order_id);
            if (!$order) continue;

            //$before = $order->get_meta('new_or_returning');
            define_new_order_customer_status($order_id, $order);
            //$after = $order->get_meta('new_or_returning');

            //$order_end = microtime(true); // ⏱️ Per-order end
            //$elapsed = round($order_end - $order_start, 4);

            /*
            if ($before !== $after) {
                $changed++;
                $this->log_message("🟡 Order ID {$order_id} changed from '{$before}' to '{$after}' ({$elapsed}s)");
            } else {
                $this->log_message("🔵 Order ID {$order_id} status remains '{$before}' ({$elapsed}s)");
            }
            */

            $processed++;
        }

        $function_end = microtime(true); // 🔴 Total timing end
        $total_time = round($function_end - $function_start, 3);

        echo "<p>✅ Customer status check completed for {$date}</p>";
        echo "<p>Processed: {$processed} orders. Changed: {$changed}. Time taken: {$total_time} seconds.</p>";

        $this->log_message("✅ Finished processing {$processed} orders ({$changed} updated) in {$total_time} seconds.");
    }



    private function process_inactive_users() {
        require_once __DIR__ . '/google_sheets/vendor/autoload.php';

        $client = new \Google_Client();
        $client->setApplicationName('Process Inactive Users');
        $client->setScopes([\Google_Service_Sheets::SPREADSHEETS]);
        $client->setAccessType('offline');
        $client->setAuthConfig(__DIR__ . '/google_sheets/credentials.json');

        $service = new Google_Service_Sheets($client);
        $spreadsheetId = '1fYrJC1_LAHJqaT1NyWvi1y6LHUTUbj7_jdN67_p1bKo';
        $range = 'A30002:A40712';

        try {
            $response = $service->spreadsheets_values->get($spreadsheetId, $range);
            $values = $response->getValues();

            if (empty($values)) {
                echo '<p>No data found in the sheet.</p>';
                return;
            }

            $csv_rows = [];
            $csv_rows[] = ['Email', 'Last Order Date', 'Products Purchased'];

            global $wpdb;

            foreach ($values as $row) {
                $email = sanitize_email(trim($row[0]));
                if (empty($email)) continue;

                echo "<h2>User: {$email}</h2>";

                $user = get_user_by('email', $email);
                $customer_id = $user ? $user->ID : 0;
                if (!$user) {
                    echo "<p style='color: orange;'>No registered user found — checking archives only.</p>";
                }

                $all_orders = [];

                // === LIVE ORDERS VIA DIRECT SQL (HPOS)
                if ($user) {
                    $orders = $wpdb->get_results($wpdb->prepare(
                        "
                    SELECT id, date_created_gmt
                    FROM {$wpdb->prefix}wc_orders
                    WHERE customer_id = %d
                    AND status NOT IN ('wc-failed', 'trash', 'auto-draft')
                    ORDER BY date_created_gmt DESC
                    ",
                        $customer_id
                    ), ARRAY_A);

                    foreach ($orders as $order_data) {
                        $order_id = $order_data['id'];
                        $order_date = date('Y-m-d H:i:s', strtotime($order_data['date_created_gmt']) + (get_option('gmt_offset') * 3600));

                        $items = $wpdb->get_results($wpdb->prepare(
                            "
                        SELECT order_item_name
                        FROM {$wpdb->prefix}woocommerce_order_items
                        WHERE order_id = %d AND order_item_type = 'line_item'
                        ",
                            $order_id
                        ));

                        $product_names = array_map(fn($r) => $r->order_item_name, $items);

                        $all_orders[] = [
                            'id' => $order_id,
                            'date' => $order_date,
                            'products' => $product_names,
                            'source' => 'live'
                        ];
                    }
                }

                // === ARCHIVED ORDERS
                $archived_orders_raw = $wpdb->get_results($wpdb->prepare(
                    "
                SELECT p.ID, p.post_date
                FROM yom_archive_orders_posts p
                INNER JOIN yom_archive_orders_postmeta pm ON p.ID = pm.post_id
                WHERE p.post_type = 'shop_order'
                  AND p.post_status NOT IN ('wc-failed', 'trash', 'auto-draft')
                  AND pm.meta_key = '_billing_email'
                  AND pm.meta_value = %s
                ",
                    $email
                ), ARRAY_A);

                foreach ($archived_orders_raw as $archived_order) {
                    $archived_id = (int)$archived_order['ID'];
                    $archived_date = $archived_order['post_date'];

                    $items = $wpdb->get_results($wpdb->prepare(
                        "
                    SELECT order_item_name
                    FROM yom_archive_orders_woocommerce_order_items
                    WHERE order_id = %d
                      AND order_item_type = 'line_item'
                    ",
                        $archived_id
                    ));

                    $product_names = array_map(fn($row) => $row->order_item_name, $items);

                    $all_orders[] = [
                        'id' => $archived_id,
                        'date' => $archived_date,
                        'products' => $product_names,
                        'source' => 'archived'
                    ];
                }

                // === NO ORDERS CASE
                if (empty($all_orders)) {
                    echo "<p>No orders found for this user.</p><hr>";
                    $csv_rows[] = [$email, '-', '-'];
                    continue;
                }

                // === Sort + Display
                usort($all_orders, fn($a, $b) => strtotime($b['date']) <=> strtotime($a['date']));
                $last_order_date = $all_orders[0]['date'];
                $all_products = [];

                echo '<table style="border-collapse: collapse; width: 100%; margin-bottom: 10px;">';
                echo '<tr>
                <th style="border: 1px solid #ccc; padding: 6px;">Order ID</th>
                <th style="border: 1px solid #ccc; padding: 6px;">Date</th>
                <th style="border: 1px solid #ccc; padding: 6px;">Source</th>
              </tr>';

                foreach ($all_orders as $entry) {
                    echo "<tr>
                    <td style='border: 1px solid #ccc; padding: 6px;'>{$entry['id']}</td>
                    <td style='border: 1px solid #ccc; padding: 6px;'>{$entry['date']}</td>
                    <td style='border: 1px solid #ccc; padding: 6px;'>{$entry['source']}</td>
                  </tr>";
                    $all_products = array_merge($all_products, $entry['products']);
                }

                echo '</table>';
                echo "<p><strong>Last Order Date:</strong> {$last_order_date}</p>";

                $unique_products = array_unique($all_products);
                $csv_rows[] = [$email, $last_order_date, implode(', ', $unique_products)];

                echo '<p><strong>Products Purchased:</strong></p><ul>';
                foreach ($unique_products as $product_name) {
                    echo '<li>' . esc_html($product_name) . '</li>';
                }
                echo '</ul><hr>';
            }

            // === WRITE CSV FILE ===
            $upload_dir = wp_upload_dir();
            $csv_file = $upload_dir['basedir'] . '/inactive_users_export.csv';

            $fp = fopen($csv_file, 'w');
            foreach ($csv_rows as $row) {
                fputcsv($fp, $row);
            }
            fclose($fp);

            echo '<p><strong>CSV generated:</strong> <a href="' . esc_url($upload_dir['baseurl'] . '/inactive_users_export.csv') . '" target="_blank">Download it here</a></p>';
        } catch (Exception $e) {
            echo '<p>Error fetching data: ' . esc_html($e->getMessage()) . '</p>';
        }
    }




    private function filter_orders_with_time_offset($inc_orders, $base_date, $post_type = "shop_order") {
        $time_zone_offset_seconds = 4 * 3600;
        $filtered_orders_result = [];
        foreach ($inc_orders as $order_id) {
            global $wpdb;
            $order_date_gmt = $this->get_order_date_gmt($order_id, $post_type);
            $order_timestamp = strtotime($order_date_gmt);
            $adjusted_order_date = $order_timestamp - $time_zone_offset_seconds;

            // Format the adjusted date for comparison
            $adjusted_order_date_formatted = date('Y-m-d', $adjusted_order_date);

            // Compare adjusted order date to the base date
            if ($adjusted_order_date_formatted === $base_date) {
                $filtered_orders_result[] = $order_id; // Add to the filtered list if it matches the base date
            }
        }

        return $filtered_orders_result;
    }


    private function get_cur_rates() {
        $start_time_get_cur_rates = microtime(true);
        $last_updated = get_option('export_stats_rates_last_updated');
        $current_date = date('Y-m-d');

        if ($last_updated === $current_date) {
            $json_rates = get_option('export_stats_currency_rates');
            $rates = json_decode($json_rates);
        } else {
            $curl = curl_init();
            $url = "https://v6.exchangerate-api.com/v6/871e5e2ef51033185690c90e/latest/USD";

            curl_setopt_array($curl, [
                CURLOPT_URL => $url,
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_FOLLOWLOCATION => true,
                CURLOPT_ENCODING => "",
                CURLOPT_MAXREDIRS => 10,
                CURLOPT_TIMEOUT => 30,
                CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
                CURLOPT_CUSTOMREQUEST => "GET",
                CURLOPT_HTTPHEADER => [],
            ]);

            $response = curl_exec($curl);
            $err = curl_error($curl);

            curl_close($curl);

            if ($err) {
                echo "cURL Error #:" . $err;
                return;
            } else {
                $rates = json_decode($response);
            }

            $json_rates = json_encode($rates);
            update_option('export_stats_currency_rates', $json_rates);
            update_option('export_stats_rates_last_updated', $current_date);
        }
        return $rates;
    }


    function get_rate($currencyCode, $currencyRates) {
        // Check if the currency code exists in the conversion rates
        if (property_exists($currencyRates->conversion_rates, $currencyCode)) {
            // Return the exchange rate for the given currency code
            return $currencyRates->conversion_rates->$currencyCode;
        } else {
            // Return null or some default value if the currency code is not found
            return null;
        }
    }

    public function show_stats($base_date = null) {
        try {
            if (null === $base_date) {
                $base_date = date('Y-m-d'); // Use current date if none is provided
            }

            $start_date = date('Y-m-d H:i:s', strtotime('-1 hours', strtotime($base_date)));
            $end_date = date('Y-m-d H:i:s', strtotime('+1 hours', strtotime($start_date)));

            $rates = $this->get_cur_rates();


            $order_args = array(
                'limit'        => -1,
                'status'       => array('wc-completed', 'wc-processing', 'wc-refunded', 'wc-on-hold'),
                'date_created' => $start_date . "..." . $end_date,
                'return'       => 'ids',
            );
            $orders = wc_get_orders($order_args);
            $orders = $this->filter_orders_with_time_offset($orders, $base_date);

            $first_order_id = !empty($orders) ? $orders[0] : '';
            $last_order_id  = !empty($orders) ? $orders[count($orders) - 1] : '';

            $this->log_message("First ID: " . ($first_order_id ?: 'N/A') . " | Last ID: " . ($last_order_id ?: 'N/A'));

            $total_sales = 0;
            $total_taxes = 0;
            $units_sold = 0;
            $total_orders = 0;
            $new_customers = 0; // Initialize new customers counter

            $new_gravite_non_subscription = 0;
            $new_non_gravite_non_subscription = 0;
            $new_subscriptions = 0;

            global $wpdb;

            foreach ($orders as $order_id) {
                // Get total quantity of items in the order (only line items)
                $items_in_order = $this->get_order_line_item_qty_sum($order_id);

                if (empty($items_in_order) || $items_in_order <= 0) {
                    continue;
                }

                $total_orders++;

                // Fetch order meta data
                $meta_keys  = array('new_or_returning', '_subscription_parent', '_subscription_renewal');
                $order_meta = $this->get_order_meta($order_id, $meta_keys);



                // Log the entire meta array first, just to see what we got

                // Correctly extract each meta key (it's just a string, no ->meta_value).

                $new_or_returning = isset($order_meta['new_or_returning']) ? $order_meta['new_or_returning'] : '';

                $order = wc_get_order($order_id);
                $order_total = $order ? floatval($order->get_total()) : 0;
                $tax = $order ? floatval($order->get_total_tax()) : 0;
                $order_currency = $order ? $order->get_currency() : '';

                // Calculate exchange rate
                $exchange_rate = $this->get_rate($order_currency, $rates);
                if ($exchange_rate) {
                    $order_total = $order_total / $exchange_rate;
                    $tax = $tax / $exchange_rate;
                }

                // Do not subtract refunded amount here to match original code
                $net_order_total = $order_total;
                $total_sales += $net_order_total;

                $total_taxes += $tax;
                $units_sold += $items_in_order;



                if ($new_or_returning === 'new') {
                    $new_customers++;

                    $is_subscription = !empty($order_meta['_subscription_renewal']) || !empty($order_meta['_subscription_parent']);

                    if (!empty($order_meta['_subscription_parent'])) {
                        $new_subscriptions++;
                    }

                    if (!$is_subscription) {
                        $items = $order->get_items('line_item');

                        $only_gravite = true;
                        $has_gravite = false;

                        foreach ($items as $item) {
                            $product = $item->get_product();
                            if (!$product) {
                                $only_gravite = false;
                                continue;
                            }

                            $sku = $product->get_sku();

                            if ($sku !== '860005339785') {
                                $only_gravite = false;
                            } else {
                                $has_gravite = true;
                            }
                        }

                        if ($only_gravite) {
                            $new_gravite_non_subscription++;
                        } else {
                            $new_non_gravite_non_subscription++;
                        }
                    }
                }
            }
            $refund_args = array(
                'limit'        => -1,
                'type'         => 'shop_order_refund',
                'date_created' => $start_date . '...' . $end_date,
                'return'       => 'ids',
            );
            $refunds = wc_get_orders($refund_args);

            $refunds = $this->filter_orders_with_time_offset($refunds, $base_date, 'shop_order_refund');

            $total_refunds = 0;


            foreach ($refunds as $refund_id) {
                $refund = wc_get_order($refund_id);
                $refund_amount = abs($refund->get_amount());

                $order_currency = $refund->get_currency();
                $exchange_rate = $this->get_rate($order_currency, $rates);
                if ($exchange_rate) {
                    $refund_amount = $refund_amount / $exchange_rate;
                }
                $total_refunds += $refund_amount;
            }


            $net_revenue = $total_sales - $total_refunds - $total_taxes;


            $current_time = date('Y-m-d H:i:s', strtotime('+3 hours'));
            $domain = $_SERVER['HTTP_HOST'];

            $data_to_export = [
                $current_time . "| Domain: " . $domain,
                "",
                $net_revenue,
                $total_refunds,
                $new_customers,
                "",
                $total_orders,
                $units_sold,
            ];

            $media_data_to_export = [
                $new_gravite_non_subscription,
                $new_subscriptions,
                $new_non_gravite_non_subscription,
            ];

            $originalDate = DateTime::createFromFormat('Y-m-d', $base_date);
            $convertedDate = $originalDate->format('m/d/Y');

            $this->add_data_for_date($convertedDate, $data_to_export);
            $this->add_media_data_for_date($convertedDate, $media_data_to_export);
        } catch (Exception $e) {
            // Log the exception
            $this->log_error('Error in show_stats function: ' . $e->getMessage());
            // Optionally, send an email or perform another form of notification
        }
    }



    function removeElementByValue(array &$array, $valueToRemove): void {
        $key = array_search($valueToRemove, $array);
        if ($key !== false) {
            unset($array[$key]);
        }
        $array = array_values($array);
    }

    private function log_error($message) {
        // Get the plugin directory path
        $plugin_dir_path = plugin_dir_path(__FILE__);

        // Define the error log file path
        $log_file = $plugin_dir_path . 'errors.txt';

        // Create a timestamp for the log entry
        $timestamp = date('Y-m-d H:i:s');

        // Format the log message
        $log_message = "{$timestamp}: {$message}\n";

        // Write the log message to the file, append if file already exists
        file_put_contents($log_file, $log_message, FILE_APPEND);

        // Optionally, you can email the error or perform another form of notification
        // wp_mail($to, $subject, $log_message);
    }


    function add_data_for_date($base_date, $data_to_export) {
        require __DIR__ . '/google_sheets/vendor/autoload.php';
        $client = new \Google_Client();

        $data_to_export = array_map(function ($item) {
            return $item === "" ? Google_Model::NULL_VALUE : $item;
        }, $data_to_export);

        // Set up the Google Client
        $client->setApplicationName('Stats to Google Sheets');
        $client->setScopes([\Google_Service_Sheets::SPREADSHEETS]);
        $client->setAccessType('offline');
        $client->setAuthConfig(__DIR__ . '/google_sheets/credentials.json');

        $dateObject = DateTime::createFromFormat('m/d/Y', $base_date);
        $sheet_name = $dateObject->format('F\'y');

        $service = new Google_Service_Sheets($client);
        $spreadsheetId = "184ugNbYIqJBiuzFHk7HgFWww7Gev5vMRW5gWWmwk5l4"; // Your spreadsheet ID

        $rowNumber = $this->find_row_by_date($service, $spreadsheetId, $base_date, $sheet_name);
        if ($rowNumber !== null) {
            $this->update_data_in_row($service, $spreadsheetId, $rowNumber, $data_to_export, $sheet_name);
        } else {
            //$this->insert_data_as_new_row($service, $spreadsheetId, $base_date, $data_to_export, $sheet_name);
        }
    }

    public function add_media_data_for_date($base_date, $media_data_to_export) {
        require __DIR__ . '/google_sheets/vendor/autoload.php';

        $client = new \Google_Client();
        $client->setApplicationName('Stats to Google Sheets');
        $client->setScopes([\Google_Service_Sheets::SPREADSHEETS]);
        $client->setAccessType('offline');
        $client->setAuthConfig(__DIR__ . '/google_sheets/credentials.json');

        $dateObject = DateTime::createFromFormat('m/d/Y', $base_date);
        $sheet_name = "MEDIA_" . $dateObject->format("F'y");

        $service = new Google_Service_Sheets($client);
        $spreadsheetId = "184ugNbYIqJBiuzFHk7HgFWww7Gev5vMRW5gWWmwk5l4";

        $day = intval($dateObject->format('j')); // Day of the month (1–31)
        $row = 39 + $day; // So July 1 = 40, July 2 = 41, etc.
        $range = "{$sheet_name}!B{$row}:D{$row}";

        $body = new Google_Service_Sheets_ValueRange([
            'values' => [$media_data_to_export]
        ]);

        $params = ['valueInputOption' => 'RAW'];
        $service->spreadsheets_values->update($spreadsheetId, $range, $body, $params);
    }

    function insert_data_as_new_row($service, $spreadsheetId, $date, $data, $sheet_name) {

        $range = $sheet_name; // Specify the sheet name
        $valueRange = new Google_Service_Sheets_ValueRange();

        // Pre-fill the date column and then add data
        $rowData = [$date];
        $rowData = array_merge($rowData, $data);

        $valueRange->setValues([$rowData]); // Data array
        $options = ['valueInputOption' => 'RAW'];

        // Append the data
        $service->spreadsheets_values->append($spreadsheetId, $range, $valueRange, $options);
    }


    function update_data_in_row($service, $spreadsheetId, $rowNumber, $data, $sheet_name) {

        $range = $sheet_name . '!F' . $rowNumber;
        $valueRange = new Google_Service_Sheets_ValueRange();
        $valueRange->setValues([$data]); // Data array

        $options = ['valueInputOption' => 'RAW'];
        $service->spreadsheets_values->update($spreadsheetId, $range, $valueRange, $options);
    }

    function find_row_by_date($service, $spreadsheetId, $inputDate, $sheet_name) {

        $range = $sheet_name . '!A3:A36'; // Adjust range as needed
        $response = $service->spreadsheets_values->get($spreadsheetId, $range);
        $values = $response->getValues();

        if (empty($values)) {
            return null; // No data found
        } else {
            foreach ($values as $rowIndex => $row) {
                if (!empty($row[0])) {
                    $date = DateTime::createFromFormat('l, F d, Y', $row[0]);
                    $date_formated = $date->format('m/d/Y');
                    if ($row[0] == $inputDate || $inputDate == $date_formated) {
                        return $rowIndex + 3; // +2 to align with the spreadsheet's row numbering
                    }
                }
            }
        }
        return null; // Date not found
    }

    // Activation Hook
    public function activate() {
        if (wp_get_environment_type() !== 'production') return;

        if (!wp_next_scheduled('export_stats_daily_event')) {
            $timestamp = strtotime('tomorrow 5:00 AM');
            wp_schedule_event($timestamp, 'daily', 'export_stats_daily_event');
        }
        if (!wp_next_scheduled('export_openai_daily_event')) {
            $timestamp = strtotime('tomorrow 5:30 AM');
            wp_schedule_event($timestamp, 'daily', 'export_openai_daily_event');
        }
    }

    public function export_openai_stats_to_sheets() {
        global $wpdb;
        $table_name = $wpdb->prefix . 'openai_crawlers';

        $results = $wpdb->get_results("
        SELECT
            crawler_type,
            LEFT(page_url,
                CASE
                    WHEN LOCATE('?', page_url) > 0 THEN LOCATE('?', page_url) - 1
                    ELSE LENGTH(page_url)
                END
            ) AS clean_url,
            COUNT(*) as view_count
        FROM $table_name
        GROUP BY clean_url, crawler_type
        ORDER BY view_count DESC
    ");

        if (empty($results)) {
            $this->log_error('No OpenAI crawler data found for export.');
            return;
        }

        // Prepare data
        $sheet_data = [];
        $sheet_data[] = ['Crawler Type', 'Page URL', 'Views']; // Header row
        foreach ($results as $row) {
            $sheet_data[] = [$row->crawler_type, $row->clean_url, $row->view_count];
        }

        // Export
        $this->send_openai_data_to_sheets($sheet_data, 'OpenAI Crawlers');
    }

    private function send_openai_data_to_sheets($data, $sheetName) {
        require __DIR__ . '/google_sheets/vendor/autoload.php';

        $client = new \Google_Client();
        $client->setApplicationName('OpenAI Export');
        $client->setScopes([\Google_Service_Sheets::SPREADSHEETS]);
        $client->setAccessType('offline');
        $client->setAuthConfig(__DIR__ . '/google_sheets/credentials.json');

        $service = new Google_Service_Sheets($client);
        $spreadsheetId = '1NCtlM0_QblXBIWmxqKc8u8eJrl_0zwIExcoYrbueBXM';

        // Clear the full sheet first
        $range = $sheetName . '!A1:Z1000';
        $service->spreadsheets_values->clear($spreadsheetId, $range, new Google_Service_Sheets_ClearValuesRequest());

        // Write the main data starting at A1 (row 1)
        $body = new Google_Service_Sheets_ValueRange(['values' => $data]);
        $params = ['valueInputOption' => 'RAW'];
        $service->spreadsheets_values->update($spreadsheetId, $sheetName . '!A1', $body, $params);

        // Format timestamp: Tue, May 27 2025 — 18:13
        $now = new DateTime('now', new DateTimeZone('UTC'));
        $now->modify('+3 hours');
        $formattedTime = $now->format('D, M j Y — H:i');

        // Write timestamp directly to D1
        $timestampBody = new Google_Service_Sheets_ValueRange([
            'range' => $sheetName . '!D1',
            'values' => [['Last updated: ' . $formattedTime]]
        ]);
        $service->spreadsheets_values->update(
            $spreadsheetId,
            $timestampBody->range,
            $timestampBody,
            ['valueInputOption' => 'RAW']
        );
    }


    // Deactivation Hook
    public function deactivate() {
        $timestamp = wp_next_scheduled('export_stats_hourly_event');
        wp_unschedule_event($timestamp, 'export_stats_hourly_event');

        $timestamp = wp_next_scheduled('export_stats_daily_event');
        wp_unschedule_event($timestamp, 'export_stats_daily_event');
    }









    /************************************************************/
    /*                 HPOS-AWARE HELPER FUNCTIONS              */
    /************************************************************/

    // 1) Safely get an order’s GMT date from old or new tables, returning a string (e.g. "2023-04-05 10:22:01")
    private function get_order_date_gmt($order_id, $post_type = 'shop_order') {
        global $wpdb;

        // Try old wp_posts table
        $order_date_gmt = $wpdb->get_var(
            $wpdb->prepare(
                "SELECT post_date_gmt
                 FROM {$wpdb->posts}
                 WHERE ID = %d
                   AND post_type = %s",
                $order_id,
                $post_type
            )
        );

        if ($order_date_gmt) {
            return $order_date_gmt;
        }


        // Check if HPOS table exists
        $tbl_orders = $wpdb->prefix . 'wc_orders';
        $tbl_exists = $wpdb->get_var("SHOW TABLES LIKE '{$tbl_orders}'");

        if ($tbl_exists === $tbl_orders) {
            // Try to fetch from HPOS table
            $sql = $wpdb->prepare(
                "SELECT date_created_gmt
                 FROM {$tbl_orders}
                 WHERE id = %d",
                $order_id
            );

            $order_date_gmt = $wpdb->get_var($sql);
        }

        return $order_date_gmt;
    }



    // 2) Safely get meta from old or new order-meta tables, combining if needed.
    // Returns an associative array, e.g. [ '_order_total' => '123.45', ... ]
    private function get_order_meta($order_id, $meta_keys = array()) {
        global $wpdb;
        $meta_array = [];

        // Attempt old postmeta
        if (!empty($meta_keys)) {
            $placeholders = implode(',', array_fill(0, count($meta_keys), '%s'));
            $params       = array_merge([$order_id], $meta_keys);

            $old_results = $wpdb->get_results(
                $wpdb->prepare(
                    "
                SELECT meta_key, meta_value
                FROM {$wpdb->postmeta}
                WHERE post_id = %d
                  AND meta_key IN ($placeholders)",
                    $params
                ),
                OBJECT_K
            );

            if (!empty($old_results)) {
                foreach ($old_results as $row) {
                    $meta_array[$row->meta_key] = $row->meta_value;
                }
            }
        }

        // Now also grab from HPOS if table exists, so we *combine* (in case partial migration)
        $tbl = $wpdb->prefix . 'wc_orders_meta';
        $tbl_exists = $wpdb->get_var("SHOW TABLES LIKE '{$tbl}'");
        if ($tbl_exists == $tbl) {
            if (!empty($meta_keys)) {
                $placeholders = implode(',', array_fill(0, count($meta_keys), '%s'));
                $params       = array_merge([$order_id], $meta_keys);

                $new_results = $wpdb->get_results(
                    $wpdb->prepare(
                        "
                    SELECT meta_key, meta_value
                    FROM {$tbl}
                    WHERE order_id = %d
                      AND meta_key IN ($placeholders)",
                        $params
                    ),
                    OBJECT_K
                );

                if (!empty($new_results)) {
                    foreach ($new_results as $row) {
                        $meta_array[$row->meta_key] = $row->meta_value;
                    }
                }
            }
        }

        return $meta_array;
    }


    // 3) Safely sum up line-item quantities from old or new table, combining them if found in both
    private function get_order_line_item_qty_sum($order_id) {
        global $wpdb;

        $total_qty = 0;

        $table_items = $wpdb->prefix . 'woocommerce_order_items';
        $table_meta  = $wpdb->prefix . 'woocommerce_order_itemmeta';

        // Check if tables exist
        $items_table_exists = $wpdb->get_var("SHOW TABLES LIKE '{$table_items}'") === $table_items;
        $meta_table_exists  = $wpdb->get_var("SHOW TABLES LIKE '{$table_meta}'") === $table_meta;


        if (!$items_table_exists || !$meta_table_exists) {
            return 0;
        }

        // Grab individual line items for debugging
        $results = $wpdb->get_results($wpdb->prepare("
            SELECT oim.meta_value AS qty, oi.order_item_id
            FROM {$table_items} AS oi
            INNER JOIN {$table_meta} AS oim
                ON oi.order_item_id = oim.order_item_id
            WHERE oi.order_id = %d
              AND oi.order_item_type = 'line_item'
              AND oim.meta_key = '_qty'
        ", $order_id));

        if (empty($results)) {
            return 0;
        }

        foreach ($results as $row) {
            $qty = intval($row->qty);
            $total_qty += $qty;
        }

        return $total_qty;
    }





    public function log_message($data) {
        if (!function_exists('WP_Filesystem')) {
            require_once ABSPATH . 'wp-admin/includes/file.php';
        }

        WP_Filesystem();

        global $wp_filesystem;

        $plugin_dir = plugin_dir_path(__FILE__);
        $log_file = $plugin_dir . 'my_log.txt';

        $current_time = current_time('Y-m-d H:i:s');

        // Format the data appropriately
        if (is_array($data) || is_object($data)) {
            $formatted_data = print_r($data, true);
        } else {
            $formatted_data = (string)$data;
        }

        $log_entry = "[{$current_time}] {$formatted_data}\n";

        if ($wp_filesystem->exists($log_file)) {
            $existing_content = $wp_filesystem->get_contents($log_file);
            $wp_filesystem->put_contents($log_file, $existing_content . $log_entry);
        } else {
            $wp_filesystem->put_contents($log_file, $log_entry);
        }
    }
}


// Initialize the plugin
$export_stats = new Export_stats();
