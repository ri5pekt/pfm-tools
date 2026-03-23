<?php

/**
 * Plugin Name: PFM Tools Utils
 * Description: Fast REST API endpoints for PFM Tools order comparison and processing.
 * Version: 1.0.0
 * Author: Denis Bogdanov
 */

if (! defined('ABSPATH')) {
    exit; // No direct access.
}

class PFM_Tools_Utils {

    /**
     * REST API namespace.
     */
    const REST_NAMESPACE = 'pfm-tools/v1';

    /**
     * Hardcoded API credentials (used via Basic Auth: key:secret).
     * For internal tooling only.
     */
    private const API_KEY    = 'ck_597bfb235fcc35a4386fbe0c34fd7e72def53b20';
    private const API_SECRET = 'cs_2f9188de18d63a3b1a3d937b84400e263c937c1b';

    /**
     * Timezone used for date filtering.
     * Set to America/New_York to match Metorik timezone.
     * Metorik uses America/New_York timezone (EDT = UTC-4 in summer, EST = UTC-5 in winter).
     * Orders shown in Metorik as "Oct 1, 2025 12:05 AM" are stored in WooCommerce as UTC,
     * but Metorik displays them in America/New_York timezone.
     * Example: Order 3312544 shows as Oct 1, 2025 12:05 AM in Metorik = Oct 1, 2025 04:05:27 UTC
     */
    private const METORIK_TZ = 'America/New_York';

    public function __construct() {
        add_action('rest_api_init', array($this, 'register_rest_routes'));
    }

    /**
     * Register REST API routes.
     */
    public function register_rest_routes() {
        register_rest_route(
            self::REST_NAMESPACE,
            '/orders',
            array(
                'methods'             => 'GET',
                'callback'            => array($this, 'get_orders'),
                'permission_callback' => array($this, 'check_permissions'),
                'args'                => array(
                    'date_after' => array(
                        'required'    => false,
                        'type'        => 'string',
                        'description' => 'Filter orders created after this datetime in Metorik timezone (YYYY-MM-DD HH:MM:SS).',
                    ),
                    'date_before' => array(
                        'required'    => false,
                        'type'        => 'string',
                        'description' => 'Filter orders created before this datetime in Metorik timezone (YYYY-MM-DD HH:MM:SS).',
                    ),
                    'per_page'   => array(
                        'required'    => false,
                        'type'        => 'integer',
                        'default'     => 100,
                        'description' => 'Number of orders per page.',
                    ),
                    'page'       => array(
                        'required'    => false,
                        'type'        => 'integer',
                        'default'     => 1,
                        'description' => 'Page number.',
                    ),
                ),
            )
        );

        register_rest_route(
            self::REST_NAMESPACE,
            '/orders/(?P<id>\d+)/refunds',
            array(
                'methods'             => 'GET',
                'callback'            => array($this, 'get_order_refunds'),
                'permission_callback' => array($this, 'check_permissions'),
                'args'                => array(
                    'id' => array(
                        'required'    => true,
                        'type'        => 'integer',
                        'description' => 'Order ID.',
                    ),
                ),
            )
        );


        register_rest_route(
            self::REST_NAMESPACE,
            '/refunds',
            array(
                'methods'             => 'GET',
                'callback'            => array($this, 'get_refunds'),
                'permission_callback' => array($this, 'check_permissions'),
                'args'                => array(
                    'date_after' => array(
                        'required'    => false,
                        'type'        => 'string',
                        'description' => 'Filter refunds created after this datetime in Metorik timezone (YYYY-MM-DD HH:MM:SS).',
                    ),
                    'date_before' => array(
                        'required'    => false,
                        'type'        => 'string',
                        'description' => 'Filter refunds created before this datetime in Metorik timezone (YYYY-MM-DD HH:MM:SS).',
                    ),
                    'per_page'   => array(
                        'required'    => false,
                        'type'        => 'integer',
                        'default'     => 100,
                        'description' => 'Number of refunds per page.',
                    ),
                    'page'       => array(
                        'required'    => false,
                        'type'        => 'integer',
                        'default'     => 1,
                        'description' => 'Page number.',
                    ),
                ),
            )
        );

        // Daily Orders Data endpoint - optimized for daily orders export
        register_rest_route(
            self::REST_NAMESPACE,
            '/daily-orders-data',
            array(
                'methods'             => 'GET',
                'callback'            => array($this, 'get_daily_orders_data'),
                'permission_callback' => array($this, 'check_permissions'),
                'args'                => array(
                    'date_after' => array(
                        'required'    => false,
                        'type'        => 'string',
                        'description' => 'Filter orders/refunds created after this datetime in Metorik timezone (America/New_York) (YYYY-MM-DD HH:MM:SS).',
                    ),
                    'date_before' => array(
                        'required'    => false,
                        'type'        => 'string',
                        'description' => 'Filter orders/refunds created before this datetime in Metorik timezone (America/New_York) (YYYY-MM-DD HH:MM:SS).',
                    ),
                    'per_page'   => array(
                        'required'    => false,
                        'type'        => 'integer',
                        'default'     => 300,
                        'description' => 'Number of orders per page.',
                    ),
                    'page'       => array(
                        'required'    => false,
                        'type'        => 'integer',
                        'default'     => 1,
                        'description' => 'Page number.',
                    ),
                ),
            )
        );

        register_rest_route(
            self::REST_NAMESPACE,
            '/refunds/batch',
            array(
                'methods'             => 'GET',
                'callback'            => array($this, 'get_refunds_batch'),
                'permission_callback' => array($this, 'check_permissions'),
                'args'                => array(
                    'order_ids' => array(
                        'required'    => true,
                        'type'        => 'string',
                        'description' => 'Comma-separated list of order IDs to fetch refunds for (e.g., "123,456,789"). Maximum 100 order IDs per request.',
                    ),
                ),
            )
        );

        // YT Influencers Orders endpoint - orders with UTM campaign, coupons, and line items
        register_rest_route(
            self::REST_NAMESPACE,
            '/yt-influencers-orders',
            array(
                'methods'             => 'GET',
                'callback'            => array($this, 'get_yt_influencers_orders'),
                'permission_callback' => array($this, 'check_permissions'),
                'args'                => array(
                    'date_after' => array(
                        'required'    => false,
                        'type'        => 'string',
                        'description' => 'Filter orders created after this datetime in Metorik timezone (America/New_York) (YYYY-MM-DD HH:MM:SS).',
                    ),
                    'date_before' => array(
                        'required'    => false,
                        'type'        => 'string',
                        'description' => 'Filter orders created before this datetime in Metorik timezone (America/New_York) (YYYY-MM-DD HH:MM:SS).',
                    ),
                    'per_page' => array(
                        'required'    => false,
                        'type'        => 'integer',
                        'default'     => 300,
                        'description' => 'Number of orders per page.',
                    ),
                    'page' => array(
                        'required'    => false,
                        'type'        => 'integer',
                        'default'     => 1,
                        'description' => 'Page number.',
                    ),
                ),
            )
        );

        // Daily Product Sales endpoint - returns product-level aggregated data
        register_rest_route(
            self::REST_NAMESPACE,
            '/daily-product-sales',
            array(
                'methods'             => 'GET',
                'callback'            => array($this, 'get_daily_product_sales'),
                'permission_callback' => array($this, 'check_permissions'),
                'args'                => array(
                    'date_after' => array(
                        'required'    => false,
                        'type'        => 'string',
                        'description' => 'Filter orders created after this datetime in Metorik timezone (America/New_York) (YYYY-MM-DD HH:MM:SS).',
                    ),
                    'date_before' => array(
                        'required'    => false,
                        'type'        => 'string',
                        'description' => 'Filter orders created before this datetime in Metorik timezone (America/New_York) (YYYY-MM-DD HH:MM:SS).',
                    ),
                    'per_page'   => array(
                        'required'    => false,
                        'type'        => 'integer',
                        'default'     => 300,
                        'description' => 'Number of products per page.',
                    ),
                    'page'       => array(
                        'required'    => false,
                        'type'        => 'integer',
                        'default'     => 1,
                        'description' => 'Page number.',
                    ),
                ),
            )
        );
    }




    /**
     * Simple Basic Auth check using hardcoded credentials.
     * Accepts only requests with correct key:secret in Authorization header.
     */
    public function check_permissions($request) {

        $auth_header = '';

        // Prefer custom header to avoid WordPress core intercepting standard Authorization header
        if (! empty($_SERVER['HTTP_X_PFM_AUTHORIZATION'])) {
            $auth_header = $_SERVER['HTTP_X_PFM_AUTHORIZATION'];
        } elseif (! empty($_SERVER['HTTP_AUTHORIZATION'])) {
            $auth_header = $_SERVER['HTTP_AUTHORIZATION'];
        } elseif (! empty($_SERVER['REDIRECT_HTTP_AUTHORIZATION'])) {
            $auth_header = $_SERVER['REDIRECT_HTTP_AUTHORIZATION'];
        }

        if (! $auth_header || strpos($auth_header, 'Basic ') !== 0) {
            return new WP_Error(
                'rest_forbidden',
                'Authentication required',
                array('status' => 401)
            );
        }

        $decoded = base64_decode(substr($auth_header, 6));

        if (! $decoded || strpos($decoded, ':') === false) {
            return new WP_Error(
                'rest_forbidden',
                'Invalid Authorization header',
                array('status' => 401)
            );
        }

        list($key, $secret) = explode(':', $decoded, 2);
        $key    = trim($key);
        $secret = trim($secret);

        if ($key === self::API_KEY && $secret === self::API_SECRET) {
            return true;
        }

        return new WP_Error(
            'rest_forbidden',
            'Invalid credentials',
            array('status' => 403)
        );
    }

    /**
     * Orders endpoint.
     * - Interprets date_after/date_before in Metorik timezone (e.g. America/New_York).
     * - Converts to UTC timestamps for wc_get_orders (so it matches Metorik’s day boundaries).
     * - Returns minimal order data for speed.
     */
    public function get_orders($request) {

        if (! class_exists('WooCommerce')) {
            return new WP_Error(
                'woocommerce_not_active',
                'WooCommerce is not active',
                array('status' => 500)
            );
        }

        $date_after     = $request->get_param('date_after');
        $date_before    = $request->get_param('date_before');
        $per_page       = absint($request->get_param('per_page'));
        $page           = absint($request->get_param('page'));


        if ($per_page <= 0) {
            $per_page = 100;
        }

        if ($page <= 0) {
            $page = 1;
        }

        $args = array(
            'limit'   => $per_page,
            'page'    => $page,
            'orderby' => 'date',
            'order'   => 'ASC',
            'return'  => 'ids',
            'status'  => array('wc-processing', 'wc-completed', 'wc-refunded', 'wc-on-hold'),
            'type'    => 'shop_order',
        );

        // Interpret incoming dates in Metorik timezone, then use UTC timestamps.
        if ($date_after || $date_before) {
            $metorik_tz = new DateTimeZone(self::METORIK_TZ);

            if ($date_after && $date_before) {
                $after_date  = $this->parse_date_in_timezone($date_after, $metorik_tz);
                $before_date = $this->parse_date_in_timezone($date_before, $metorik_tz);

                if ($after_date && $before_date) {
                    // Add 1 second to before_date timestamp to ensure we include orders created at exactly 23:59:59
                    // WooCommerce's date_created filter with "..." syntax is inclusive on both ends,
                    // but adding 1 second ensures we capture the entire end-of-day second
                    // Also, WooCommerce stores dates in UTC, so we need to ensure the range covers the entire day
                    // when converted from America/New_York to UTC
                    $after_timestamp = $after_date->getTimestamp();
                    $before_timestamp = $before_date->getTimestamp() + 1;
                    $args['date_created'] = $after_timestamp . '...' . $before_timestamp;
                }
            } elseif ($date_after) {
                $after_date = $this->parse_date_in_timezone($date_after, $metorik_tz);
                if ($after_date) {
                    $args['date_created'] = '>=' . $after_date->getTimestamp();
                }
            } elseif ($date_before) {
                $before_date = $this->parse_date_in_timezone($date_before, $metorik_tz);
                if ($before_date) {
                    $args['date_created'] = '<=' . $before_date->getTimestamp();
                }
            }
        }

        // Fetch all orders (filtering will be done in Python after fetching all pages)
        // This ensures pagination works correctly
        $order_ids = wc_get_orders($args);

        // Total for pagination (unfiltered - filtering happens client-side)
        $count_args           = $args;
        $count_args['limit']  = -1;
        $count_args['return'] = 'ids';
        $total                = count(wc_get_orders($count_args));

        $formatted_orders = array();

        // Get currency rates once for all orders (more efficient)
        $rates = $this->get_cur_rates();

        // Process orders and include refunds in response
        // Note: Higher per_page values (200-300) reduce API calls but increase memory usage.
        // Each order with refunds is ~1-2KB, so 300 orders ≈ 300-600KB response size.
        // This is manageable for most PHP setups, but monitor memory if increasing further.
        foreach ($order_ids as $order_id) {
            $order = wc_get_order($order_id);
            if (! $order) {
                continue;
            }

            $order_currency = $order->get_currency();
            $order_total = (float) $order->get_total();

            // Load refund objects (works for both partial and full refunds)
            $refunds = $order->get_refunds();

            // True if there is at least one refund object OR status is fully refunded
            $has_refunds = ! empty($refunds) || $order->get_status() === 'refunded';

            // Format refunds for inclusion in order response
            $formatted_refunds = array();
            foreach ($refunds as $refund) {
                $refund_amount = (float) $refund->get_amount();
                $refund_amount_usd = $this->convert_to_usd($refund_amount, $order_currency, $rates);

                $formatted_refunds[] = array(
                    'id'           => $refund->get_id(),
                    'order_id'    => $order_id,  // Parent order ID
                    'amount'       => $refund_amount_usd,
                    'reason'       => $refund->get_reason(),
                    'date_created' => $refund->get_date_created()
                        ? $refund->get_date_created()->date('Y-m-d H:i:s')
                        : null,
                );
            }

            // Convert order total to USD
            $order_total_usd = $this->convert_to_usd($order_total, $order_currency, $rates);

            $formatted_orders[] = array(
                'id'            => $order_id,  // Order ID
                'status'        => $order->get_status(),
                'date_created'  => $order->get_date_created()
                    ? $order->get_date_created()->date('Y-m-d H:i:s')
                    : null,
                'date_created_gmt' => $order->get_date_created()
                    ? gmdate('Y-m-d H:i:s', $order->get_date_created()->getTimestamp())
                    : null,
                'date_modified' => $order->get_date_modified()
                    ? $order->get_date_modified()->date('Y-m-d H:i:s')
                    : null,
                'date_paid'     => $order->get_date_paid()
                    ? $order->get_date_paid()->date('Y-m-d H:i:s')
                    : null,
                'total'         => $order_total_usd,
                'has_refunds'   => $has_refunds,
                'refunds'       => $formatted_refunds,  // Include refunds in order response
                'shipping_country' => $order->get_shipping_country(),  // For filtering (shipping address determines tax jurisdiction)
                'shipping_state'   => $order->get_shipping_state(),     // For filtering (shipping address determines tax jurisdiction)
                'billing_country' => $order->get_billing_country(),  // Keep for reference
                'billing_state'   => $order->get_billing_state(),     // Keep for reference
            );
        }


        $total_pages = ($per_page > 0) ? ceil($total / $per_page) : 1;

        $server = rest_get_server();
        $server->send_header('X-WP-Total', (int) $total);
        $server->send_header('X-WP-TotalPages', (int) $total_pages);

        return rest_ensure_response($formatted_orders);
    }

    /**
     * Refunds endpoint for a single order.
     */
    public function get_order_refunds($request) {

        if (! class_exists('WooCommerce')) {
            return new WP_Error(
                'woocommerce_not_active',
                'WooCommerce is not active',
                array('status' => 500)
            );
        }

        $order_id = absint($request->get_param('id'));

        if (! $order_id) {
            return new WP_Error(
                'invalid_order_id',
                'Invalid order ID',
                array('status' => 400)
            );
        }

        $order = wc_get_order($order_id);
        if (! $order) {
            return new WP_Error(
                'order_not_found',
                'Order not found',
                array('status' => 404)
            );
        }

        $refunds           = $order->get_refunds();
        $formatted_refunds = array();

        // Get currency rates for conversion
        $order_currency = $order->get_currency();
        $rates = $this->get_cur_rates();

        foreach ($refunds as $refund) {
            $refund_amount = (float) $refund->get_amount();
            $refund_amount_usd = $this->convert_to_usd($refund_amount, $order_currency, $rates);

            $formatted_refunds[] = array(
                'id'           => $refund->get_id(),
                'amount'       => $refund_amount_usd,
                'reason'       => $refund->get_reason(),
                'date_created' => $refund->get_date_created()
                    ? $refund->get_date_created()->date('Y-m-d H:i:s')
                    : null,
            );
        }

        return rest_ensure_response($formatted_refunds);
    }


    /**
     * Refunds endpoint (global).
     * - Interprets date_after/date_before in Metorik timezone (America/New_York).
     * - Converts to UTC timestamps for wc_get_orders on shop_order_refund.
     */
    public function get_refunds($request) {

        if (! class_exists('WooCommerce')) {
            return new WP_Error(
                'woocommerce_not_active',
                'WooCommerce is not active',
                array('status' => 500)
            );
        }

        $date_after  = $request->get_param('date_after');
        $date_before = $request->get_param('date_before');
        $per_page    = absint($request->get_param('per_page'));
        $page        = absint($request->get_param('page'));

        if ($per_page <= 0) {
            $per_page = 100;
        }

        if ($page <= 0) {
            $page = 1;
        }

        $args = array(
            'limit'   => $per_page,
            'page'    => $page,
            'orderby' => 'date',
            'order'   => 'ASC',
            'return'  => 'ids',
            'type'    => 'shop_order_refund',
        );

        // Same date-shift logic as get_orders (Metorik TZ -> UTC timestamps).
        if ($date_after || $date_before) {
            $metorik_tz = new DateTimeZone(self::METORIK_TZ);

            if ($date_after && $date_before) {
                $after_date  = $this->parse_date_in_timezone($date_after, $metorik_tz);
                $before_date = $this->parse_date_in_timezone($date_before, $metorik_tz);

                if ($after_date && $before_date) {
                    // Add 1 second to before_date timestamp to ensure we include orders created at exactly 23:59:59
                    $before_timestamp = $before_date->getTimestamp() + 1;
                    $args['date_created'] = $after_date->getTimestamp() . '...' . $before_timestamp;
                }
            } elseif ($date_after) {
                $after_date = $this->parse_date_in_timezone($date_after, $metorik_tz);
                if ($after_date) {
                    $args['date_created'] = '>=' . $after_date->getTimestamp();
                }
            } elseif ($date_before) {
                $before_date = $this->parse_date_in_timezone($date_before, $metorik_tz);
                if ($before_date) {
                    $args['date_created'] = '<=' . $before_date->getTimestamp();
                }
            }
        }

        $refund_ids = wc_get_orders($args);

        // Total for pagination.
        $count_args           = $args;
        $count_args['limit']  = -1;
        $count_args['return'] = 'ids';
        $total                = count(wc_get_orders($count_args));

        $formatted_refunds = array();

        // Get currency rates for conversion
        $rates = $this->get_cur_rates();

        foreach ($refund_ids as $refund_id) {
            $refund = wc_get_order($refund_id);
            if (! $refund) {
                continue;
            }

            $parent_id = $refund->get_parent_id();
            $parent    = $parent_id ? wc_get_order($parent_id) : null;

            $refund_currency = $refund->get_currency();
            $refund_amount = (float) $refund->get_amount();
            $refund_amount_usd = $this->convert_to_usd($refund_amount, $refund_currency, $rates);

            $formatted_refunds[] = array(
                'id'            => $refund->get_id(),
                'order_id'      => $parent_id ? (int) $parent_id : null,
                'order_number'  => $parent ? $parent->get_order_number() : null,
                'amount'        => $refund_amount_usd,
                'reason'        => $refund->get_reason(),
                'currency'      => $refund_currency,
                'date_created'  => $refund->get_date_created()
                    ? $refund->get_date_created()->date('Y-m-d H:i:s')
                    : null,
            );
        }

        $total_pages = ($per_page > 0) ? ceil($total / $per_page) : 1;

        $server = rest_get_server();
        $server->send_header('X-WP-Total', (int) $total);
        $server->send_header('X-WP-TotalPages', (int) $total_pages);

        return rest_ensure_response($formatted_refunds);
    }

    /**
     * Batch refunds endpoint.
     * Accepts comma-separated order IDs and returns all refunds for those orders in a single call.
     * This is much faster than making individual API calls for each order.
     */
    public function get_refunds_batch($request) {

        if (! class_exists('WooCommerce')) {
            return new WP_Error(
                'woocommerce_not_active',
                'WooCommerce is not active',
                array('status' => 500)
            );
        }

        $order_ids_param = $request->get_param('order_ids');

        if (! $order_ids_param) {
            return new WP_Error(
                'missing_order_ids',
                'order_ids parameter is required',
                array('status' => 400)
            );
        }

        // Parse comma-separated order IDs
        $order_ids = array_map('absint', array_filter(explode(',', $order_ids_param)));

        if (empty($order_ids)) {
            return new WP_Error(
                'invalid_order_ids',
                'No valid order IDs provided',
                array('status' => 400)
            );
        }

        // Limit to 100 order IDs per request to prevent timeouts
        if (count($order_ids) > 100) {
            return new WP_Error(
                'too_many_order_ids',
                'Maximum 100 order IDs allowed per request',
                array('status' => 400)
            );
        }

        $formatted_refunds = array();

        // Get currency rates for conversion
        $rates = $this->get_cur_rates();

        foreach ($order_ids as $order_id) {
            $order = wc_get_order($order_id);
            if (! $order) {
                continue;
            }

            $order_currency = $order->get_currency();
            $refunds = $order->get_refunds();

            foreach ($refunds as $refund) {
                $refund_amount = (float) $refund->get_amount();
                $refund_amount_usd = $this->convert_to_usd($refund_amount, $order_currency, $rates);

                $formatted_refunds[] = array(
                    'id'           => $refund->get_id(),
                    'order_id'     => $order_id,
                    'amount'       => $refund_amount_usd,
                    'reason'       => $refund->get_reason(),
                    'date_created' => $refund->get_date_created()
                        ? $refund->get_date_created()->date('Y-m-d H:i:s')
                        : null,
                );
            }
        }

        return rest_ensure_response($formatted_refunds);
    }

    /**
     * Daily Orders Data endpoint.
     * Optimized endpoint for daily orders export that returns both orders and refunds
     * with all necessary data (line items, meta, extra fields) in a single response.
     * Uses Metorik timezone (America/New_York) for date filtering to match Metorik's day boundaries.
     */
    public function get_daily_orders_data($request) {

        if (! class_exists('WooCommerce')) {
            return new WP_Error(
                'woocommerce_not_active',
                'WooCommerce is not active',
                array('status' => 500)
            );
        }

        $date_after     = $request->get_param('date_after');
        $date_before    = $request->get_param('date_before');
        $per_page       = absint($request->get_param('per_page'));
        $page           = absint($request->get_param('page'));

        if ($per_page <= 0) {
            $per_page = 300;
        }

        if ($page <= 0) {
            $page = 1;
        }

        // Parse dates in Metorik timezone (America/New_York) to match Metorik's day boundaries
        // This ensures orders for "Nov 26, 2025" match Metorik's definition of that day
        $metorik_tz = new DateTimeZone('America/New_York');

        $order_args = array(
            'limit'   => $per_page,
            'page'    => $page,
            'orderby' => 'date',
            'order'   => 'ASC',
            'return'  => 'ids',
            'status'  => array('wc-processing', 'wc-completed', 'wc-refunded', 'wc-on-hold'),
            'type'    => 'shop_order',
        );

        $refund_args = array(
            'limit'   => $per_page,
            'page'    => $page,
            'orderby' => 'date',
            'order'   => 'ASC',
            'return'  => 'ids',
            'type'    => 'shop_order_refund',
        );

        // Parse dates in Metorik timezone (America/New_York), then convert to UTC timestamps for WooCommerce
        // WooCommerce stores dates in UTC, so we need to convert Metorik timezone dates to UTC timestamps
        if ($date_after || $date_before) {
            if ($date_after && $date_before) {
                $after_date  = $this->parse_date_in_timezone($date_after, $metorik_tz);
                $before_date = $this->parse_date_in_timezone($date_before, $metorik_tz);

                if ($after_date && $before_date) {
                    // Add 1 second to before_date timestamp to ensure we include orders created at exactly 23:59:59
                    $after_timestamp = $after_date->getTimestamp();
                    $before_timestamp = $before_date->getTimestamp() + 1;
                    $order_args['date_created'] = $after_timestamp . '...' . $before_timestamp;
                    $refund_args['date_created'] = $after_timestamp . '...' . $before_timestamp;
                }
            } elseif ($date_after) {
                $after_date = $this->parse_date_in_timezone($date_after, $metorik_tz);
                if ($after_date) {
                    $order_args['date_created'] = '>=' . $after_date->getTimestamp();
                    $refund_args['date_created'] = '>=' . $after_date->getTimestamp();
                }
            } elseif ($date_before) {
                $before_date = $this->parse_date_in_timezone($date_before, $metorik_tz);
                if ($before_date) {
                    $order_args['date_created'] = '<=' . $before_date->getTimestamp();
                    $refund_args['date_created'] = '<=' . $before_date->getTimestamp();
                }
            }
        }

        // Fetch orders
        $order_ids = wc_get_orders($order_args);
        $count_order_args = $order_args;
        $count_order_args['limit'] = -1;
        $count_order_args['return'] = 'ids';
        $total_orders = count(wc_get_orders($count_order_args));

        // Fetch refunds
        $refund_ids = wc_get_orders($refund_args);
        $count_refund_args = $refund_args;
        $count_refund_args['limit'] = -1;
        $count_refund_args['return'] = 'ids';
        $total_refunds = count(wc_get_orders($count_refund_args));

        $formatted_orders = array();
        $formatted_refunds = array();

        // Get currency rates once for all orders and refunds (more efficient)
        $rates = $this->get_cur_rates();

        // Process orders with all necessary data
        foreach ($order_ids as $order_id) {
            $order = wc_get_order($order_id);
            if (! $order) {
                continue;
            }

            $order_currency = $order->get_currency();

            // Load refund objects
            $refunds = $order->get_refunds();
            $has_refunds = ! empty($refunds) || $order->get_status() === 'refunded';

            // Format refunds for inclusion in order response
            $order_refunds = array();
            foreach ($refunds as $refund) {
                $refund_amount = (float) $refund->get_amount();
                $refund_amount_usd = $this->convert_to_usd($refund_amount, $order_currency, $rates);

                $order_refunds[] = array(
                    'id'           => $refund->get_id(),
                    'order_id'    => $order_id,  // Parent order ID
                    'amount'       => $refund_amount_usd,
                    'reason'       => $refund->get_reason(),
                    'date_created' => $refund->get_date_created()
                        ? $refund->get_date_created()->date('Y-m-d H:i:s')
                        : null,
                );
            }

            // Get line items with quantities and SKUs
            $formatted_line_items = array();
            $total_units = 0;
            foreach ($order->get_items('line_item') as $item_id => $item) {
                $product = $item->get_product();
                $sku = $product ? $product->get_sku() : '';
                $qty = (int) $item->get_quantity();
                $total_units += $qty;

                $formatted_line_items[] = array(
                    'item_id'   => $item_id,
                    'name'      => $item->get_name(),
                    'quantity'  => $qty,
                    'sku'       => $sku,
                );
            }

            // Get order meta fields
            $new_or_returning = $order->get_meta('new_or_returning');
            $subscription_parent = $order->get_meta('_subscription_parent');
            $subscription_renewal = $order->get_meta('_subscription_renewal');

            // Convert all monetary amounts to USD
            $order_total = (float) $order->get_total();
            $order_total_tax = (float) $order->get_total_tax();
            $order_shipping_total = (float) $order->get_shipping_total();
            $order_discount_total = (float) $order->get_discount_total();

            $order_total_usd = $this->convert_to_usd($order_total, $order_currency, $rates);
            $order_total_tax_usd = $this->convert_to_usd($order_total_tax, $order_currency, $rates);
            $order_shipping_total_usd = $this->convert_to_usd($order_shipping_total, $order_currency, $rates);
            $order_discount_total_usd = $this->convert_to_usd($order_discount_total, $order_currency, $rates);

            $formatted_orders[] = array(
                'id'            => $order->get_id(),
                'status'        => $order->get_status(),
                'date_created'  => $order->get_date_created()
                    ? $order->get_date_created()->date('Y-m-d H:i:s')
                    : null,
                'date_created_gmt' => $order->get_date_created()
                    ? gmdate('Y-m-d H:i:s', $order->get_date_created()->getTimestamp())
                    : null,
                'date_modified' => $order->get_date_modified()
                    ? $order->get_date_modified()->date('Y-m-d H:i:s')
                    : null,
                'date_paid'     => $order->get_date_paid()
                    ? $order->get_date_paid()->date('Y-m-d H:i:s')
                    : null,
                'total'         => $order_total_usd,
                'total_tax'     => $order_total_tax_usd,
                'shipping_total' => $order_shipping_total_usd,
                'discount_total' => $order_discount_total_usd,
                'currency'      => $order_currency,
                'has_refunds'   => $has_refunds,
                'refunds'       => $order_refunds,
                'line_items'    => $formatted_line_items,
                'total_units'   => $total_units,
                'new_or_returning' => $new_or_returning ?: '',
                'subscription_parent' => $subscription_parent ?: '',
                'subscription_renewal' => $subscription_renewal ?: '',
                'shipping_country' => $order->get_shipping_country(),
                'shipping_state'   => $order->get_shipping_state(),
                'billing_country' => $order->get_billing_country(),
                'billing_state'   => $order->get_billing_state(),
            );
        }

        // Process refunds separately (standalone refunds)
        foreach ($refund_ids as $refund_id) {
            $refund = wc_get_order($refund_id);
            if (! $refund) {
                continue;
            }

            $parent_id = $refund->get_parent_id();
            $parent    = $parent_id ? wc_get_order($parent_id) : null;

            $refund_currency = $refund->get_currency();
            $refund_amount = (float) $refund->get_amount();
            $refund_amount_usd = $this->convert_to_usd($refund_amount, $refund_currency, $rates);

            $formatted_refunds[] = array(
                'id'            => $refund->get_id(),
                'order_id'      => $parent_id ? (int) $parent_id : null,
                'order_number'  => $parent ? $parent->get_order_number() : null,
                'amount'        => $refund_amount_usd,
                'reason'        => $refund->get_reason(),
                'currency'      => $refund_currency,
                'date_created'  => $refund->get_date_created()
                    ? $refund->get_date_created()->date('Y-m-d H:i:s')
                    : null,
            );
        }

        // Calculate pagination
        $total_order_pages = ($per_page > 0) ? ceil($total_orders / $per_page) : 1;
        $total_refund_pages = ($per_page > 0) ? ceil($total_refunds / $per_page) : 1;

        $server = rest_get_server();
        $server->send_header('X-WP-Total-Orders', (int) $total_orders);
        $server->send_header('X-WP-Total-OrderPages', (int) $total_order_pages);
        $server->send_header('X-WP-Total-Refunds', (int) $total_refunds);
        $server->send_header('X-WP-Total-RefundPages', (int) $total_refund_pages);

        return rest_ensure_response(array(
            'orders' => $formatted_orders,
            'refunds' => $formatted_refunds,
            'pagination' => array(
                'orders' => array(
                    'total' => $total_orders,
                    'pages' => $total_order_pages,
                    'page' => $page,
                    'per_page' => $per_page,
                ),
                'refunds' => array(
                    'total' => $total_refunds,
                    'pages' => $total_refund_pages,
                    'page' => $page,
                    'per_page' => $per_page,
                ),
            ),
        ));
    }


    /**
     * Helper: parse a date string in a given timezone.
     * Accepts "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD".
     */
    private function parse_date_in_timezone($date_string, DateTimeZone $timezone) {
        try {
            $date = DateTime::createFromFormat('Y-m-d H:i:s', $date_string, $timezone);

            if (! $date) {
                $date = DateTime::createFromFormat('Y-m-d', $date_string, $timezone);
                if ($date) {
                    $date->setTime(0, 0, 0);
                }
            }

            return $date ?: false;
        } catch (Exception $e) {
            return false;
        }
    }

    /**
     * Get currency exchange rates from API and cache them for the day.
     * Returns rates object with conversion_rates property.
     *
     * @return object|null Currency rates object or null on error.
     */
    private function get_cur_rates() {
        $last_updated = get_option('pfm_tools_utils_rates_last_updated');
        $current_date = date('Y-m-d');

        if ($last_updated === $current_date) {
            $json_rates = get_option('pfm_tools_utils_currency_rates');
            $rates = json_decode($json_rates);
            if ($rates) {
                return $rates;
            }
        }

        // Fetch fresh rates from API
        $curl = curl_init();
        $url = "https://v6.exchangerate-api.com/v6/871e5e2ef51033185690c90e/latest/USD";

        curl_setopt_array($curl, array(
            CURLOPT_URL => $url,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_FOLLOWLOCATION => true,
            CURLOPT_ENCODING => "",
            CURLOPT_MAXREDIRS => 10,
            CURLOPT_TIMEOUT => 30,
            CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
            CURLOPT_CUSTOMREQUEST => "GET",
            CURLOPT_HTTPHEADER => array(),
        ));

        $response = curl_exec($curl);
        $err = curl_error($curl);

        curl_close($curl);

        if ($err) {
            $this->log_message("Currency API cURL Error: " . $err);
            return null;
        }

        $rates = json_decode($response);
        if ($rates && isset($rates->conversion_rates)) {
            $json_rates = json_encode($rates);
            update_option('pfm_tools_utils_currency_rates', $json_rates);
            update_option('pfm_tools_utils_rates_last_updated', $current_date);
            return $rates;
        }

        return null;
    }

    /**
     * Get exchange rate for a specific currency code.
     *
     * @param string $currencyCode The currency code (e.g., 'EUR', 'GBP').
     * @param object $currencyRates The rates object from get_cur_rates().
     * @return float|null Exchange rate or null if not found.
     */
    private function get_rate($currencyCode, $currencyRates) {
        if (! $currencyRates || ! isset($currencyRates->conversion_rates)) {
            return null;
        }

        // Check if the currency code exists in the conversion rates
        if (property_exists($currencyRates->conversion_rates, $currencyCode)) {
            // Return the exchange rate for the given currency code
            return $currencyRates->conversion_rates->$currencyCode;
        }

        // Return null if the currency code is not found
        return null;
    }

    /**
     * Convert amount from original currency to USD.
     *
     * @param float $amount The amount in original currency.
     * @param string $currencyCode The currency code of the original amount.
     * @param object|null $rates Optional rates object. If not provided, will fetch fresh rates.
     * @return float Amount in USD.
     */
    private function convert_to_usd($amount, $currencyCode, $rates = null) {
        // If already USD, no conversion needed
        if ($currencyCode === 'USD') {
            return $amount;
        }

        // Get rates if not provided
        if ($rates === null) {
            $rates = $this->get_cur_rates();
        }

        if (! $rates) {
            return $amount; // Return original if rates unavailable
        }

        $exchange_rate = $this->get_rate($currencyCode, $rates);
        if ($exchange_rate && $exchange_rate > 0) {
            return $amount / $exchange_rate;
        }

        // Return original amount if conversion fails
        return $amount;
    }

    /**
     * YT Influencers Orders endpoint.
     * Returns completed/processing orders with: order total (USD), _wc_order_attribution_utm_campaign meta,
     * applied coupon codes, and line items (name + quantity).
     * Uses Metorik timezone (America/New_York) for date filtering.
     */
    public function get_yt_influencers_orders($request) {

        if (! class_exists('WooCommerce')) {
            return new WP_Error('woocommerce_not_active', 'WooCommerce is not active', array('status' => 500));
        }

        $date_after  = $request->get_param('date_after');
        $date_before = $request->get_param('date_before');
        $per_page    = max(1, absint($request->get_param('per_page')));
        $page        = max(1, absint($request->get_param('page')));

        $metorik_tz = new DateTimeZone(self::METORIK_TZ);

        $args = array(
            'limit'   => $per_page,
            'page'    => $page,
            'orderby' => 'date',
            'order'   => 'ASC',
            'return'  => 'ids',
            'status'  => array('wc-processing', 'wc-completed', 'wc-refunded', 'wc-on-hold'),
            'type'    => 'shop_order',
        );

        if ($date_after && $date_before) {
            $after_date  = $this->parse_date_in_timezone($date_after, $metorik_tz);
            $before_date = $this->parse_date_in_timezone($date_before, $metorik_tz);
            if ($after_date && $before_date) {
                $args['date_created'] = $after_date->getTimestamp() . '...' . ($before_date->getTimestamp() + 1);
            }
        } elseif ($date_after) {
            $after_date = $this->parse_date_in_timezone($date_after, $metorik_tz);
            if ($after_date) {
                $args['date_created'] = '>=' . $after_date->getTimestamp();
            }
        } elseif ($date_before) {
            $before_date = $this->parse_date_in_timezone($date_before, $metorik_tz);
            if ($before_date) {
                $args['date_created'] = '<=' . $before_date->getTimestamp();
            }
        }

        $order_ids = wc_get_orders($args);

        $count_args           = $args;
        $count_args['limit']  = -1;
        $count_args['return'] = 'ids';
        $total                = count(wc_get_orders($count_args));

        $rates = $this->get_cur_rates();

        $formatted_orders = array();

        foreach ($order_ids as $order_id) {
            $order = wc_get_order($order_id);
            if (! $order) {
                continue;
            }

            $order_currency  = $order->get_currency();
            $order_total     = (float) $order->get_total();
            $order_total_usd = $this->convert_to_usd($order_total, $order_currency, $rates);

            // UTM campaign stored by Metorik
            $utm_campaign = $order->get_meta('_wc_order_attribution_utm_campaign');

            // Coupon codes applied to this order
            $coupon_codes = $order->get_coupon_codes();

            // Line items: product name + quantity only
            $line_items = array();
            foreach ($order->get_items('line_item') as $item) {
                $line_items[] = array(
                    'name'     => $item->get_name(),
                    'quantity' => (int) $item->get_quantity(),
                );
            }

            $formatted_orders[] = array(
                'id'           => $order->get_id(),
                'date_created' => $order->get_date_created()
                    ? $order->get_date_created()->date('Y-m-d H:i:s')
                    : null,
                'total'        => $order_total_usd,
                'utm_campaign' => $utm_campaign ?: '',
                'coupon_codes' => $coupon_codes,
                'line_items'   => $line_items,
            );
        }

        $total_pages = ($per_page > 0) ? (int) ceil($total / $per_page) : 1;

        $server = rest_get_server();
        $server->send_header('X-WP-Total', (int) $total);
        $server->send_header('X-WP-TotalPages', (int) $total_pages);

        return rest_ensure_response(array(
            'orders'     => $formatted_orders,
            'pagination' => array(
                'total'    => $total,
                'pages'    => $total_pages,
                'page'     => $page,
                'per_page' => $per_page,
            ),
        ));
    }


    /**
     * Daily Product Sales endpoint.
     * Returns product-level aggregated data (SKU, product name, gross sales, orders count, items count).
     * Uses Metorik timezone (America/New_York) for date filtering.
     */
    public function get_daily_product_sales($request) {

        if (! class_exists('WooCommerce')) {
            return new WP_Error(
                'woocommerce_not_active',
                'WooCommerce is not active',
                array('status' => 500)
            );
        }

        $date_after     = $request->get_param('date_after');
        $date_before    = $request->get_param('date_before');
        $per_page       = absint($request->get_param('per_page'));
        $page           = absint($request->get_param('page'));

        if ($per_page <= 0) {
            $per_page = 300;
        }

        if ($page <= 0) {
            $page = 1;
        }

        // Parse dates in Metorik timezone (America/New_York)
        $metorik_tz = new DateTimeZone('America/New_York');

        // Marketing stats mode: ignore refunds.
        // Only include paid-ish order states and do NOT subtract refunds.
        $paid_statuses = array('wc-processing', 'wc-completed', 'wc-on-hold');

        $order_args = array(
            'limit'   => $per_page,  // Paginate orders to avoid loading millions at once
            'page'    => $page,      // Current page of orders
            'orderby' => 'date',
            'order'   => 'ASC',
            'return'  => 'ids',
            'status'  => $paid_statuses,
            'type'    => 'shop_order',
        );

        // Parse dates in Metorik timezone, then convert to UTC timestamps
        if ($date_after || $date_before) {
            if ($date_after && $date_before) {
                $after_date  = $this->parse_date_in_timezone($date_after, $metorik_tz);
                $before_date = $this->parse_date_in_timezone($date_before, $metorik_tz);

                if ($after_date && $before_date) {
                    $after_timestamp = $after_date->getTimestamp();
                    $before_timestamp = $before_date->getTimestamp() + 1;
                    $order_args['date_created'] = $after_timestamp . '...' . $before_timestamp;
                }
            } elseif ($date_after) {
                $after_date = $this->parse_date_in_timezone($date_after, $metorik_tz);
                if ($after_date) {
                    $order_args['date_created'] = '>=' . $after_date->getTimestamp();
                }
            } elseif ($date_before) {
                $before_date = $this->parse_date_in_timezone($date_before, $metorik_tz);
                if ($before_date) {
                    $order_args['date_created'] = '<=' . $before_date->getTimestamp();
                }
            }
        }

        // Fetch paginated orders + totals without limit=-1 (safe for large stores).
        // wc_get_orders supports 'paginate' which returns totals and max_num_pages.
        $order_ids = array();
        $total_orders = 0;
        $total_order_pages = 1;

        $paged_args = $order_args;
        $paged_args['paginate'] = true;
        $paged_result = wc_get_orders($paged_args);

        // WooCommerce paginate() can return either an array-like structure OR an object (varies by version).
        // We support both shapes here.
        if (is_array($paged_result) && isset($paged_result['orders'])) {
            $order_ids = $paged_result['orders'];
            $total_orders = isset($paged_result['total']) ? (int) $paged_result['total'] : 0;
            $total_order_pages = isset($paged_result['max_num_pages']) ? (int) $paged_result['max_num_pages'] : 1;
        } elseif (is_object($paged_result) && isset($paged_result->orders)) {
            $order_ids = $paged_result->orders;
            $total_orders = isset($paged_result->total) ? (int) $paged_result->total : 0;
            $total_order_pages = isset($paged_result->max_num_pages) ? (int) $paged_result->max_num_pages : 1;
        } else {
            // Fallback to non-paginated return shape (older WooCommerce).
            // NOTE: This fallback cannot provide true totals safely; paginate should work on modern Woo.
            $order_ids = wc_get_orders($order_args);
            $total_orders = count($order_ids);
            $total_order_pages = ($per_page > 0) ? ceil($total_orders / $per_page) : 1;
        }

        // If the query returned WC_Order objects (unexpected when 'return' => 'ids'), normalize to IDs.
        if (! empty($order_ids) && is_object($order_ids[0]) && method_exists($order_ids[0], 'get_id')) {
            $order_ids = array_map(function ($o) {
                return $o->get_id();
            }, $order_ids);
        }

        // Get currency rates for conversion
        $rates = $this->get_cur_rates();

        // Aggregate products by SKU for this page of orders
        // Note: The Python service will aggregate across all pages
        $products_by_sku = array();

        // (Debug logging removed)

        foreach ($order_ids as $order_id) {
            $order = wc_get_order($order_id);
            if (! $order) {
                continue;
            }

            $order_currency = $order->get_currency();
            $order_date = $order->get_date_created();

            // Process line items (marketing stats: no refund subtraction).
            foreach ($order->get_items('line_item') as $item_id => $item) {
                $product = $item->get_product();
                if (! $product) {
                    continue;
                }

                $sku = $product->get_sku();
                if (empty($sku)) {
                    continue;  // Skip products without SKU
                }

                // Normalize SKU: trim whitespace and convert to string for consistent matching
                $sku = trim((string) $sku);
                if (empty($sku)) {
                    continue;  // Skip if SKU is empty after normalization
                }

                $product_name = $product->get_name();
                $quantity = (int) $item->get_quantity();
                // WooCommerce:
                // - get_subtotal(): line total BEFORE discounts (excl tax) -> use for GROSS sales
                // - get_total(): line total AFTER discounts (excl tax)
                $line_subtotal = (float) $item->get_subtotal();

                // Convert to USD
                $line_subtotal_usd = $this->convert_to_usd($line_subtotal, $order_currency, $rates);

                // Initialize product data if not exists (only set product_name on first creation)
                if (! isset($products_by_sku[$sku])) {
                    $products_by_sku[$sku] = array(
                        'sku'          => $sku,
                        'product_name' => $product_name,  // Set title only on first creation
                        // NOTE: field name kept as 'gross_sales' for backwards compatibility with Python.
                        // We store GROSS sales here (before discounts, excl tax/shipping).
                        'gross_sales'  => 0.0,
                        'order_ids'    => array(),
                        'items'        => 0,
                    );
                }

                // Aggregate data (only compare by SKU when updating)
                // GROSS sales (before discounts) for the line item.
                $products_by_sku[$sku]['gross_sales'] += $line_subtotal_usd;
                $products_by_sku[$sku]['order_ids'][] = $order_id;
                $products_by_sku[$sku]['items'] += $quantity;
            }

            // Refund handling intentionally disabled for marketing stats.
        }

        // (Debug logging removed)

        // Convert to array format
        // Note: We return all products from this page of orders (not paginated by product)
        // The Python service will aggregate products across all order pages
        $products_array = array_values($products_by_sku);

        // Remove duplicate order IDs and convert to counts
        foreach ($products_array as &$product) {
            $product['order_ids'] = array_unique($product['order_ids']);
            $unique_order_count = count($product['order_ids']);
            $product['orders_count'] = $unique_order_count;
            $product['item_orders_count'] = $unique_order_count;  // Alias for orders_count
            // IMPORTANT: Do not return full order_ids lists (can be huge across 300 orders/page).
            // Python aggregates orders by summing item_orders_count across pages (pages are disjoint by design).
            unset($product['order_ids']);
        }

        $server = rest_get_server();
        // Send headers for order pagination (not product pagination)
        $server->send_header('X-WP-Total', (int) $total_orders);
        $server->send_header('X-WP-TotalPages', (int) $total_order_pages);

        return rest_ensure_response(array(
            'products' => $products_array,  // All products from this page of orders
            'pagination' => array(
                'total' => $total_orders,      // Total orders (not products)
                'pages' => $total_order_pages, // Total order pages (not product pages)
                'page' => $page,
                'per_page' => $per_page,
            ),
        ));
    }

    /**
     * Custom logging function that writes to a .log file in the plugin directory.
     *
     * @param string $message The log message to write.
     * @return void
     */
    private function log_message($message) {
        $log_file = plugin_dir_path(__FILE__) . 'pfm-tools-utils.log';
        $timestamp = date('Y-m-d H:i:s');
        $log_entry = sprintf("[%s] %s\n", $timestamp, $message);

        // Append to log file (create if it doesn't exist)
        @file_put_contents($log_file, $log_entry, FILE_APPEND | LOCK_EX);
    }
}

new PFM_Tools_Utils();
